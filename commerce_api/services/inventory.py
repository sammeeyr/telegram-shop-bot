from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_api.db.models import (
    InventoryBalance,
    Product,
    ProductVariant,
    ReservationStatus,
    StockMovement,
    StockMovementKind,
    StockReservation,
    Warehouse,
    utcnow,
)
from commerce_api.services.errors import (
    Conflict,
    IdempotencyConflict,
    InsufficientStock,
    InvalidQuantity,
    ResourceNotFound,
)

MAX_RESERVATION_SECONDS = 7 * 24 * 60 * 60


def _validate_quantity(quantity: Decimal) -> None:
    if not quantity.is_finite() or quantity <= 0 or max(0, -quantity.as_tuple().exponent) > 3:
        raise InvalidQuantity("Quantity must be positive with at most three decimal places")


async def _ensure_location(session: AsyncSession, tenant_id: UUID, variant_id: UUID, warehouse_id: UUID) -> None:
    variant = await session.scalar(
        select(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(
            ProductVariant.tenant_id == tenant_id,
            ProductVariant.id == variant_id,
            ProductVariant.is_active.is_(True),
        )
    )
    warehouse = await session.scalar(
        select(Warehouse).where(
            Warehouse.tenant_id == tenant_id,
            Warehouse.id == warehouse_id,
            Warehouse.is_active.is_(True),
        )
    )
    if variant is None or warehouse is None:
        raise ResourceNotFound("Active variant or warehouse not found")


async def _get_balance(
    session: AsyncSession, tenant_id: UUID, variant_id: UUID, warehouse_id: UUID, *, lock: bool = False
) -> InventoryBalance | None:
    stmt = select(InventoryBalance).where(
        InventoryBalance.tenant_id == tenant_id,
        InventoryBalance.variant_id == variant_id,
        InventoryBalance.warehouse_id == warehouse_id,
    )
    if lock:
        stmt = stmt.with_for_update()
    return await session.scalar(stmt)


async def _ensure_balance(
    session: AsyncSession, tenant_id: UUID, variant_id: UUID, warehouse_id: UUID
) -> InventoryBalance:
    values = {
        "id": uuid4(),
        "tenant_id": tenant_id,
        "variant_id": variant_id,
        "warehouse_id": warehouse_id,
        "on_hand": Decimal("0"),
        "reserved": Decimal("0"),
        "safety_stock": Decimal("0"),
        "updated_at": utcnow(),
    }
    insert = pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    await session.execute(
        insert(InventoryBalance)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["tenant_id", "variant_id", "warehouse_id"])
    )
    balance = await _get_balance(session, tenant_id, variant_id, warehouse_id, lock=True)
    assert balance is not None
    return balance


def _movement(
    *, tenant_id, variant_id, warehouse_id, kind: str, quantity: Decimal,
    idempotency_key: str, actor_user_id, reason: str = "", reservation_id=None,
) -> StockMovement:
    return StockMovement(
        tenant_id=tenant_id,
        variant_id=variant_id,
        warehouse_id=warehouse_id,
        reservation_id=reservation_id,
        actor_user_id=actor_user_id,
        kind=kind,
        quantity=quantity,
        idempotency_key=idempotency_key,
        reason=reason,
    )


async def set_safety_stock(
    session: AsyncSession, *, tenant_id: UUID, variant_id: UUID, warehouse_id: UUID, quantity: Decimal
) -> InventoryBalance:
    if not quantity.is_finite() or quantity < 0 or max(0, -quantity.as_tuple().exponent) > 3:
        raise InvalidQuantity("Safety stock must be nonnegative with at most three decimal places")
    await _ensure_location(session, tenant_id, variant_id, warehouse_id)
    balance = await _ensure_balance(session, tenant_id, variant_id, warehouse_id)
    balance.safety_stock = quantity
    balance.updated_at = utcnow()
    await session.flush()
    return balance


async def receive_stock(
    session: AsyncSession, *, tenant_id: UUID, variant_id: UUID, warehouse_id: UUID,
    quantity: Decimal, idempotency_key: str, actor_user_id: UUID, reason: str = "",
) -> tuple[InventoryBalance, StockMovement]:
    _validate_quantity(quantity)
    existing = await session.scalar(
        select(StockMovement).where(
            StockMovement.tenant_id == tenant_id,
            StockMovement.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if (
            existing.kind != StockMovementKind.RECEIPT
            or existing.variant_id != variant_id
            or existing.warehouse_id != warehouse_id
            or existing.quantity != quantity
        ):
            raise IdempotencyConflict("Idempotency key was already used for a different stock movement")
        balance = await _get_balance(session, tenant_id, variant_id, warehouse_id)
        return balance, existing

    await _ensure_location(session, tenant_id, variant_id, warehouse_id)
    balance = await _ensure_balance(session, tenant_id, variant_id, warehouse_id)
    balance.on_hand += quantity
    balance.updated_at = utcnow()
    movement = _movement(
        tenant_id=tenant_id,
        variant_id=variant_id,
        warehouse_id=warehouse_id,
        kind=StockMovementKind.RECEIPT,
        quantity=quantity,
        idempotency_key=idempotency_key,
        actor_user_id=actor_user_id,
        reason=reason,
    )
    session.add(movement)
    await session.flush()
    return balance, movement


async def adjust_stock(
    session: AsyncSession, *, tenant_id: UUID, variant_id: UUID, warehouse_id: UUID,
    delta: Decimal, idempotency_key: str, actor_user_id: UUID, reason: str,
) -> tuple[InventoryBalance, StockMovement]:
    if not delta.is_finite() or delta == 0 or max(0, -delta.as_tuple().exponent) > 3:
        raise InvalidQuantity("Adjustment must be nonzero with at most three decimal places")
    direction = "increase" if delta > 0 else "decrease"
    movement_reason = f"{direction}: {reason}"[:240]
    existing = await session.scalar(
        select(StockMovement).where(
            StockMovement.tenant_id == tenant_id,
            StockMovement.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if (
            existing.kind != StockMovementKind.ADJUSTMENT
            or existing.variant_id != variant_id
            or existing.warehouse_id != warehouse_id
            or existing.quantity != abs(delta)
            or existing.reason != movement_reason
        ):
            raise IdempotencyConflict("Idempotency key was already used for a different stock movement")
        balance = await _get_balance(session, tenant_id, variant_id, warehouse_id)
        return balance, existing

    await _ensure_location(session, tenant_id, variant_id, warehouse_id)
    await _ensure_balance(session, tenant_id, variant_id, warehouse_id)
    where = [
        InventoryBalance.tenant_id == tenant_id,
        InventoryBalance.variant_id == variant_id,
        InventoryBalance.warehouse_id == warehouse_id,
    ]
    if delta < 0:
        where.append(InventoryBalance.on_hand - InventoryBalance.reserved - InventoryBalance.safety_stock >= abs(delta))
    updated = await session.scalar(
        update(InventoryBalance)
        .where(*where)
        .values(on_hand=InventoryBalance.on_hand + delta, updated_at=utcnow())
        .returning(InventoryBalance.id)
    )
    if updated is None:
        raise InsufficientStock("Adjustment would reduce stock below reserved and safety quantities")
    movement = _movement(
        tenant_id=tenant_id,
        variant_id=variant_id,
        warehouse_id=warehouse_id,
        kind=StockMovementKind.ADJUSTMENT,
        quantity=abs(delta),
        idempotency_key=idempotency_key,
        actor_user_id=actor_user_id,
        reason=movement_reason,
    )
    session.add(movement)
    await session.flush()
    return await _get_balance(session, tenant_id, variant_id, warehouse_id), movement


async def return_stock(
    session: AsyncSession, *, tenant_id: UUID, variant_id: UUID, warehouse_id: UUID,
    quantity: Decimal, idempotency_key: str, actor_user_id: UUID, reason: str = "",
) -> tuple[InventoryBalance, StockMovement]:
    _validate_quantity(quantity)
    existing = await session.scalar(
        select(StockMovement).where(
            StockMovement.tenant_id == tenant_id,
            StockMovement.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if (
            existing.kind != StockMovementKind.RETURN
            or existing.variant_id != variant_id
            or existing.warehouse_id != warehouse_id
            or existing.quantity != quantity
        ):
            raise IdempotencyConflict("Idempotency key was already used for a different stock movement")
        balance = await _get_balance(session, tenant_id, variant_id, warehouse_id)
        return balance, existing

    await _ensure_location(session, tenant_id, variant_id, warehouse_id)
    balance = await _ensure_balance(session, tenant_id, variant_id, warehouse_id)
    balance.on_hand += quantity
    balance.updated_at = utcnow()
    movement = _movement(
        tenant_id=tenant_id,
        variant_id=variant_id,
        warehouse_id=warehouse_id,
        kind=StockMovementKind.RETURN,
        quantity=quantity,
        idempotency_key=idempotency_key,
        actor_user_id=actor_user_id,
        reason=reason,
    )
    session.add(movement)
    await session.flush()
    return balance, movement


async def transfer_stock(
    session: AsyncSession, *, tenant_id: UUID, variant_id: UUID, source_warehouse_id: UUID,
    destination_warehouse_id: UUID, quantity: Decimal, idempotency_key: str,
    actor_user_id: UUID, reason: str = "",
) -> tuple[InventoryBalance, InventoryBalance]:
    _validate_quantity(quantity)
    if source_warehouse_id == destination_warehouse_id:
        raise InvalidQuantity("Source and destination warehouses must differ")
    transfer_key = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    out_key, in_key = f"transfer:{transfer_key}:out", f"transfer:{transfer_key}:in"
    existing = list(
        (
            await session.scalars(
                select(StockMovement).where(
                    StockMovement.tenant_id == tenant_id,
                    StockMovement.idempotency_key.in_([out_key, in_key]),
                )
            )
        ).all()
    )
    if existing:
        outgoing = next((movement for movement in existing if movement.idempotency_key == out_key), None)
        incoming = next((movement for movement in existing if movement.idempotency_key == in_key), None)
        if (
            outgoing is None
            or incoming is None
            or outgoing.variant_id != variant_id
            or incoming.variant_id != variant_id
            or outgoing.warehouse_id != source_warehouse_id
            or incoming.warehouse_id != destination_warehouse_id
            or outgoing.quantity != quantity
            or incoming.quantity != quantity
        ):
            raise IdempotencyConflict("Idempotency key was already used for a different stock movement")
        source = await _get_balance(session, tenant_id, variant_id, source_warehouse_id)
        destination = await _get_balance(session, tenant_id, variant_id, destination_warehouse_id)
        return source, destination

    await _ensure_location(session, tenant_id, variant_id, source_warehouse_id)
    await _ensure_location(session, tenant_id, variant_id, destination_warehouse_id)
    balances: dict[UUID, InventoryBalance] = {}
    for warehouse_id in sorted((source_warehouse_id, destination_warehouse_id), key=str):
        balances[warehouse_id] = await _ensure_balance(session, tenant_id, variant_id, warehouse_id)

    source_update = await session.scalar(
        update(InventoryBalance)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.variant_id == variant_id,
            InventoryBalance.warehouse_id == source_warehouse_id,
            InventoryBalance.on_hand - InventoryBalance.reserved - InventoryBalance.safety_stock >= quantity,
        )
        .values(on_hand=InventoryBalance.on_hand - quantity, updated_at=utcnow())
        .returning(InventoryBalance.id)
    )
    if source_update is None:
        raise InsufficientStock("Insufficient available stock to transfer")
    await session.execute(
        update(InventoryBalance)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.variant_id == variant_id,
            InventoryBalance.warehouse_id == destination_warehouse_id,
        )
        .values(on_hand=InventoryBalance.on_hand + quantity, updated_at=utcnow())
    )
    session.add_all(
        [
            _movement(
                tenant_id=tenant_id,
                variant_id=variant_id,
                warehouse_id=source_warehouse_id,
                kind=StockMovementKind.TRANSFER,
                quantity=quantity,
                idempotency_key=out_key,
                actor_user_id=actor_user_id,
                reason=f"out:{destination_warehouse_id}:{reason}"[:240],
            ),
            _movement(
                tenant_id=tenant_id,
                variant_id=variant_id,
                warehouse_id=destination_warehouse_id,
                kind=StockMovementKind.TRANSFER,
                quantity=quantity,
                idempotency_key=in_key,
                actor_user_id=actor_user_id,
                reason=f"in:{source_warehouse_id}:{reason}"[:240],
            ),
        ]
    )
    await session.flush()
    return (
        await _get_balance(session, tenant_id, variant_id, source_warehouse_id),
        await _get_balance(session, tenant_id, variant_id, destination_warehouse_id),
    )


async def reserve_stock(
    session: AsyncSession, *, tenant_id: UUID, variant_id: UUID, warehouse_id: UUID,
    quantity: Decimal, idempotency_key: str, actor_user_id: UUID, expires_in_seconds: int = 900,
) -> StockReservation:
    _validate_quantity(quantity)
    if not 60 <= expires_in_seconds <= MAX_RESERVATION_SECONDS:
        raise InvalidQuantity("Reservation expiry must be between 60 seconds and 7 days")

    existing = await session.scalar(
        select(StockReservation).where(
            StockReservation.tenant_id == tenant_id,
            StockReservation.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if (
            existing.variant_id != variant_id
            or existing.warehouse_id != warehouse_id
            or existing.quantity != quantity
        ):
            raise IdempotencyConflict("Idempotency key was already used for a different reservation")
        return existing

    await _ensure_location(session, tenant_id, variant_id, warehouse_id)
    reservation_id = uuid4()
    now = utcnow()
    values = {
        "id": reservation_id,
        "tenant_id": tenant_id,
        "variant_id": variant_id,
        "warehouse_id": warehouse_id,
        "quantity": quantity,
        "idempotency_key": idempotency_key,
        "status": ReservationStatus.ACTIVE,
        "expires_at": now + timedelta(seconds=expires_in_seconds),
        "created_at": now,
    }
    insert = pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    created_id = await session.scalar(
        insert(StockReservation)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["tenant_id", "idempotency_key"])
        .returning(StockReservation.id)
    )
    if created_id is None:
        existing = await session.scalar(
            select(StockReservation).where(
                StockReservation.tenant_id == tenant_id,
                StockReservation.idempotency_key == idempotency_key,
            )
        )
        if existing is None:
            raise IdempotencyConflict("Reservation idempotency key could not be resolved")
        if (
            existing.variant_id != variant_id
            or existing.warehouse_id != warehouse_id
            or existing.quantity != quantity
        ):
            raise IdempotencyConflict("Idempotency key was already used for a different reservation")
        return existing

    balance_id = await session.scalar(
        update(InventoryBalance)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.variant_id == variant_id,
            InventoryBalance.warehouse_id == warehouse_id,
            InventoryBalance.on_hand - InventoryBalance.reserved - InventoryBalance.safety_stock >= quantity,
        )
        .values(reserved=InventoryBalance.reserved + quantity, updated_at=now)
        .returning(InventoryBalance.id)
    )
    if balance_id is None:
        raise InsufficientStock("Insufficient available stock")

    reservation = await session.get(StockReservation, reservation_id)
    session.add(
        _movement(
            tenant_id=tenant_id,
            variant_id=variant_id,
            warehouse_id=warehouse_id,
            reservation_id=reservation_id,
            kind=StockMovementKind.RESERVATION,
            quantity=quantity,
            idempotency_key=f"reservation:{reservation_id}:reserve",
            actor_user_id=actor_user_id,
        )
    )
    await session.flush()
    return reservation


async def _finish_reservation(
    session: AsyncSession, *, tenant_id: UUID, reservation_id: UUID,
    actor_user_id: UUID, target_status: ReservationStatus,
) -> StockReservation:
    reservation = await session.scalar(
        select(StockReservation)
        .where(StockReservation.tenant_id == tenant_id, StockReservation.id == reservation_id)
        .with_for_update()
    )
    if reservation is None:
        raise ResourceNotFound("Reservation not found")
    if reservation.status != ReservationStatus.ACTIVE:
        return reservation

    now = utcnow()
    values = {"reserved": InventoryBalance.reserved - reservation.quantity, "updated_at": now}
    kind = StockMovementKind.RELEASE
    if target_status == ReservationStatus.DEDUCTED:
        values["on_hand"] = InventoryBalance.on_hand - reservation.quantity
        kind = StockMovementKind.DEDUCTION
        enough_stock = InventoryBalance.on_hand >= reservation.quantity
    else:
        enough_stock = True

    balance_id = await session.scalar(
        update(InventoryBalance)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.variant_id == reservation.variant_id,
            InventoryBalance.warehouse_id == reservation.warehouse_id,
            InventoryBalance.reserved >= reservation.quantity,
            enough_stock,
        )
        .values(**values)
        .returning(InventoryBalance.id)
    )
    if balance_id is None:
        raise Conflict("Inventory balance no longer matches the reservation")

    reservation.status = target_status
    reservation.completed_at = now
    session.add(
        _movement(
            tenant_id=tenant_id,
            variant_id=reservation.variant_id,
            warehouse_id=reservation.warehouse_id,
            reservation_id=reservation.id,
            kind=kind,
            quantity=reservation.quantity,
            idempotency_key=f"reservation:{reservation.id}:{target_status.value}",
            actor_user_id=actor_user_id,
        )
    )
    await session.flush()
    return reservation


async def release_reservation(
    session: AsyncSession, *, tenant_id: UUID, reservation_id: UUID, actor_user_id: UUID,
) -> StockReservation:
    return await _finish_reservation(
        session,
        tenant_id=tenant_id,
        reservation_id=reservation_id,
        actor_user_id=actor_user_id,
        target_status=ReservationStatus.RELEASED,
    )


async def deduct_reservation(
    session: AsyncSession, *, tenant_id: UUID, reservation_id: UUID, actor_user_id: UUID,
) -> StockReservation:
    return await _finish_reservation(
        session,
        tenant_id=tenant_id,
        reservation_id=reservation_id,
        actor_user_id=actor_user_id,
        target_status=ReservationStatus.DEDUCTED,
    )


async def expire_reservations(
    session: AsyncSession, *, tenant_id: UUID, actor_user_id: UUID, limit: int = 100,
) -> int:
    if not 1 <= limit <= 500:
        raise InvalidQuantity("Expiry batch limit must be between 1 and 500")
    expired = await session.scalars(
        select(StockReservation)
        .where(
            StockReservation.tenant_id == tenant_id,
            StockReservation.status == ReservationStatus.ACTIVE,
            StockReservation.expires_at <= datetime.now(UTC),
        )
        .order_by(StockReservation.expires_at, StockReservation.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    reservations = list(expired.all())
    for reservation in reservations:
        await _finish_reservation(
            session,
            tenant_id=tenant_id,
            reservation_id=reservation.id,
            actor_user_id=actor_user_id,
            target_status=ReservationStatus.EXPIRED,
        )
    return len(reservations)


async def get_balance(
    session: AsyncSession, *, tenant_id: UUID, variant_id: UUID, warehouse_id: UUID
) -> InventoryBalance:
    balance = await _get_balance(session, tenant_id, variant_id, warehouse_id)
    if balance is None:
        raise ResourceNotFound("Inventory balance not found")
    return balance


async def list_movements(
    session: AsyncSession, *, tenant_id: UUID, variant_id: UUID, offset: int, limit: int
) -> list[StockMovement]:
    rows = await session.scalars(
        select(StockMovement)
        .where(StockMovement.tenant_id == tenant_id, StockMovement.variant_id == variant_id)
        .order_by(StockMovement.created_at.desc(), StockMovement.id)
        .offset(offset)
        .limit(limit)
    )
    return list(rows.all())