from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, update

from commerce_api.db.models import InventoryBalance, StockMovement, StockReservation, Tenant, User
from commerce_api.db.rls import set_rls_context
from commerce_api.db.session import create_engine, create_session_factory
from commerce_api.schemas import CategoryCreate, ProductCreate, VariantCreate, WarehouseCreate
from commerce_api.services import catalog, inventory
from commerce_api.services.errors import InsufficientStock


@pytest.mark.asyncio
async def test_concurrent_reservations_cannot_oversell_last_unit() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL inventory concurrency tests")

    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    user_id, tenant_id = uuid4(), uuid4()
    try:
        async with session_factory() as session:
            session.add(User(id=user_id, email=f"inventory-{user_id}@test.invalid", full_name="Test", password_hash="unused"))
            await session.commit()

        async with session_factory() as session:
            async with session.begin():
                await set_rls_context(session, user_id=str(user_id), tenant_id=str(tenant_id))
                session.add(Tenant(id=tenant_id, name="Concurrency Test", slug=f"concurrency-{tenant_id.hex}"))
                await session.flush()
                category = await catalog.create_category(
                    session, tenant_id, CategoryCreate(name="Stock", slug="stock")
                )
                product = await catalog.create_product(
                    session,
                    tenant_id,
                    ProductCreate(
                        category_id=category.id,
                        name="Last Unit",
                        slug="last-unit",
                        unit_price_minor=500,
                        is_active=True,
                    ),
                )
                variant = await catalog.create_variant(
                    session, tenant_id, product.id, VariantCreate(name="Default", sku=f"SKU-{tenant_id.hex}")
                )
                warehouse = await catalog.create_warehouse(
                    session, tenant_id, WarehouseCreate(name="Primary", code=f"W-{tenant_id.hex[:20]}")
                )
                await inventory.receive_stock(
                    session,
                    tenant_id=tenant_id,
                    variant_id=variant.id,
                    warehouse_id=warehouse.id,
                    quantity=Decimal("1"),
                    idempotency_key=f"seed-{tenant_id.hex}",
                    actor_user_id=user_id,
                )
                variant_id, warehouse_id = variant.id, warehouse.id

        async def reserve_once(key: str) -> bool:
            try:
                async with session_factory() as session:
                    async with session.begin():
                        await set_rls_context(session, user_id=str(user_id), tenant_id=str(tenant_id))
                        await inventory.reserve_stock(
                            session,
                            tenant_id=tenant_id,
                            variant_id=variant_id,
                            warehouse_id=warehouse_id,
                            quantity=Decimal("1"),
                            idempotency_key=key,
                            actor_user_id=user_id,
                        )
                return True
            except InsufficientStock:
                return False

        results = await asyncio.gather(reserve_once("race-a"), reserve_once("race-b"))
        assert sorted(results) == [False, True]

        async with session_factory() as session:
            async with session.begin():
                await set_rls_context(session, user_id=str(user_id), tenant_id=str(tenant_id))
                balance = await session.scalar(
                    select(InventoryBalance).where(
                        InventoryBalance.tenant_id == tenant_id,
                        InventoryBalance.variant_id == variant_id,
                        InventoryBalance.warehouse_id == warehouse_id,
                    )
                )
                reservations = list(
                    (
                        await session.scalars(
                            select(StockReservation).where(StockReservation.tenant_id == tenant_id)
                        )
                    ).all()
                )
                movements = list(
                    (
                        await session.scalars(
                            select(StockMovement).where(StockMovement.tenant_id == tenant_id)
                        )
                    ).all()
                )
                assert balance is not None
                assert balance.on_hand == Decimal("1.000")
                assert balance.reserved == Decimal("1.000")
                assert len(reservations) == 1
                assert len(movements) == 2

        async with session_factory() as session:
            async with session.begin():
                await set_rls_context(session, user_id=str(user_id), tenant_id=str(uuid4()))
                assert list((await session.scalars(select(InventoryBalance))).all()) == []

        async with session_factory() as session:
            async with session.begin():
                await set_rls_context(session, user_id=str(user_id), tenant_id=str(tenant_id))
                await session.execute(
                    update(StockReservation)
                    .where(StockReservation.tenant_id == tenant_id)
                    .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
                )
                expired_count = await inventory.expire_reservations(
                    session, tenant_id=tenant_id, actor_user_id=user_id
                )
                assert expired_count == 1
                balance = await session.scalar(
                    select(InventoryBalance).where(InventoryBalance.tenant_id == tenant_id)
                )
                assert balance is not None
                assert balance.reserved == Decimal("0.000")
    finally:
        async with session_factory() as session:
            async with session.begin():
                await set_rls_context(session, user_id=str(user_id), tenant_id=str(tenant_id))
                await session.execute(delete(Tenant).where(Tenant.id == tenant_id))
        async with session_factory() as session:
            async with session.begin():
                await session.execute(delete(User).where(User.id == user_id))
        await engine.dispose()
