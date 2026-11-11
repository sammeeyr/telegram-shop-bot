from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_api.dependencies import TenantAdmin, get_db
from commerce_api.schemas import (
    InventoryBalanceConfigureRequest,
    InventoryBalanceResponse,
    ReservationCreateRequest,
    ReservationExpiryResponse,
    ReservationResponse,
    StockAdjustmentRequest,
    StockMovementResponse,
    StockReceiptRequest,
    StockReceiptResponse,
    StockReturnRequest,
    StockTransferRequest,
    StockTransferResponse,
)
from commerce_api.services import inventory

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _balance_response(balance) -> InventoryBalanceResponse:
    return InventoryBalanceResponse(
        id=balance.id,
        tenant_id=balance.tenant_id,
        variant_id=balance.variant_id,
        warehouse_id=balance.warehouse_id,
        on_hand=balance.on_hand,
        reserved=balance.reserved,
        available=balance.on_hand - balance.reserved - balance.safety_stock,
        safety_stock=balance.safety_stock,
        updated_at=balance.updated_at,
    )


@router.put("/balances", response_model=InventoryBalanceResponse)
async def configure_balance(
    values: InventoryBalanceConfigureRequest,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    balance = await inventory.set_safety_stock(
        session,
        tenant_id=access.tenant_id,
        variant_id=values.variant_id,
        warehouse_id=values.warehouse_id,
        quantity=values.safety_stock,
    )
    return _balance_response(balance)


@router.post("/receipts", response_model=StockReceiptResponse, status_code=201)
async def receive_stock(
    values: StockReceiptRequest,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    balance, movement = await inventory.receive_stock(
        session,
        tenant_id=access.tenant_id,
        variant_id=values.variant_id,
        warehouse_id=values.warehouse_id,
        quantity=values.quantity,
        idempotency_key=values.idempotency_key,
        actor_user_id=access.user.id,
        reason=values.reason,
    )
    return StockReceiptResponse(balance=_balance_response(balance), movement=movement)


@router.post("/adjustments", response_model=StockReceiptResponse, status_code=201)
async def adjust_stock(
    values: StockAdjustmentRequest,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    balance, movement = await inventory.adjust_stock(
        session,
        tenant_id=access.tenant_id,
        variant_id=values.variant_id,
        warehouse_id=values.warehouse_id,
        delta=values.delta,
        idempotency_key=values.idempotency_key,
        actor_user_id=access.user.id,
        reason=values.reason,
    )
    return StockReceiptResponse(balance=_balance_response(balance), movement=movement)


@router.post("/returns", response_model=StockReceiptResponse, status_code=201)
async def return_stock(
    values: StockReturnRequest,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    balance, movement = await inventory.return_stock(
        session,
        tenant_id=access.tenant_id,
        variant_id=values.variant_id,
        warehouse_id=values.warehouse_id,
        quantity=values.quantity,
        idempotency_key=values.idempotency_key,
        actor_user_id=access.user.id,
        reason=values.reason,
    )
    return StockReceiptResponse(balance=_balance_response(balance), movement=movement)


@router.post("/transfers", response_model=StockTransferResponse, status_code=201)
async def transfer_stock(
    values: StockTransferRequest,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    source, destination = await inventory.transfer_stock(
        session,
        tenant_id=access.tenant_id,
        variant_id=values.variant_id,
        source_warehouse_id=values.source_warehouse_id,
        destination_warehouse_id=values.destination_warehouse_id,
        quantity=values.quantity,
        idempotency_key=values.idempotency_key,
        actor_user_id=access.user.id,
        reason=values.reason,
    )
    return StockTransferResponse(
        source=_balance_response(source), destination=_balance_response(destination)
    )


@router.get("/balances/{warehouse_id}/{variant_id}", response_model=InventoryBalanceResponse)
async def get_balance(
    warehouse_id: UUID,
    variant_id: UUID,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    balance = await inventory.get_balance(
        session, tenant_id=access.tenant_id, variant_id=variant_id, warehouse_id=warehouse_id
    )
    return _balance_response(balance)


@router.get("/variants/{variant_id}/movements", response_model=list[StockMovementResponse])
async def list_movements(
    variant_id: UUID,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    return await inventory.list_movements(
        session, tenant_id=access.tenant_id, variant_id=variant_id, offset=offset, limit=limit
    )


@router.post("/reservations", response_model=ReservationResponse, status_code=201)
async def reserve_stock(
    values: ReservationCreateRequest,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await inventory.reserve_stock(
        session,
        tenant_id=access.tenant_id,
        variant_id=values.variant_id,
        warehouse_id=values.warehouse_id,
        quantity=values.quantity,
        idempotency_key=values.idempotency_key,
        actor_user_id=access.user.id,
        expires_in_seconds=values.expires_in_seconds,
    )


@router.post("/reservations/{reservation_id}/release", response_model=ReservationResponse)
async def release_reservation(
    reservation_id: UUID,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await inventory.release_reservation(
        session,
        tenant_id=access.tenant_id,
        reservation_id=reservation_id,
        actor_user_id=access.user.id,
    )


@router.post("/reservations/{reservation_id}/deduct", response_model=ReservationResponse)
async def deduct_reservation(
    reservation_id: UUID,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await inventory.deduct_reservation(
        session,
        tenant_id=access.tenant_id,
        reservation_id=reservation_id,
        actor_user_id=access.user.id,
    )


@router.post("/reservations/expire", response_model=ReservationExpiryResponse)
async def expire_reservations(
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    count = await inventory.expire_reservations(
        session, tenant_id=access.tenant_id, actor_user_id=access.user.id, limit=limit
    )
    return ReservationExpiryResponse(expired_count=count)