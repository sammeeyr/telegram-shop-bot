from __future__ import annotations

import os
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text

from commerce_api.db.models import (
    DigitalAsset,
    Order,
    OrderItem,
    Product,
    ProductVariant,
    Tenant,
    TenantMembership,
    User,
    Customer,
    MembershipRole,
)
from commerce_api.db.rls import set_rls_context
from commerce_api.db.session import create_engine, create_session_factory


@pytest.mark.asyncio
async def test_postgres_rls_hides_other_tenants_from_direct_queries() -> None:
    runtime_url = os.getenv("TEST_DATABASE_URL")
    if not runtime_url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL RLS integration tests")

    runtime_engine = create_engine(runtime_url)
    session_factory = create_session_factory(runtime_engine)
    user_a_id, user_b_id = uuid4(), uuid4()
    tenant_a_id, tenant_b_id = uuid4(), uuid4()
    try:
        async with session_factory() as session:
            session.add_all(
                [
                    User(id=user_a_id, email=f"{user_a_id}@test.invalid", full_name="A", password_hash="unused"),
                    User(id=user_b_id, email=f"{user_b_id}@test.invalid", full_name="B", password_hash="unused"),
                ]
            )
            await session.commit()

        for user_id, tenant_id, name in (
            (user_a_id, tenant_a_id, "Tenant A"),
            (user_b_id, tenant_b_id, "Tenant B"),
        ):
            async with session_factory() as session:
                async with session.begin():
                    await set_rls_context(session, user_id=str(user_id), tenant_id=str(tenant_id))
                    session.add(Tenant(id=tenant_id, name=name, slug=f"tenant-{tenant_id.hex}"))
                    session.add(
                        TenantMembership(
                            tenant_id=tenant_id, user_id=user_id, role=MembershipRole.OWNER.value
                        )
                    )

        order_id, order_item_id = uuid4(), uuid4()
        variant_id, customer_id = uuid4(), uuid4()
        product_id = uuid4()
        async with session_factory() as session:
            async with session.begin():
                await set_rls_context(session, user_id=str(user_a_id), tenant_id=str(tenant_a_id))
                session.add_all(
                    [
                        Customer(
                            id=customer_id,
                            tenant_id=tenant_a_id,
                            full_name="Customer A",
                        ),
                        Product(
                            id=product_id,
                            tenant_id=tenant_a_id,
                            name="Digital test item",
                            slug=f"digital-{tenant_a_id.hex}",
                            description="",
                            unit_price_minor=100,
                            currency="USD",
                            product_type="digital",
                            is_active=True,
                        ),
                    ]
                )
                await session.flush()
                session.add(
                    ProductVariant(
                        id=variant_id,
                        tenant_id=tenant_a_id,
                        product_id=product_id,
                        name="Default",
                        sku=f"DIGITAL-{tenant_a_id.hex}",
                    )
                )
                session.add(
                    Order(
                        id=order_id,
                        tenant_id=tenant_a_id,
                        customer_id=customer_id,
                        checkout_key=f"rls-{tenant_a_id.hex}",
                        source="api",
                        currency="USD",
                        subtotal_minor=100,
                        total_minor=100,
                        payment_status="pending",
                        fulfillment_status="reserved",
                    )
                )
                await session.flush()
                session.add(
                    OrderItem(
                        id=order_item_id,
                        tenant_id=tenant_a_id,
                        order_id=order_id,
                        variant_id=variant_id,
                        product_name_snapshot="Digital test item",
                        variant_name_snapshot="Default",
                        sku_snapshot=f"DIGITAL-{tenant_a_id.hex}",
                        product_type="digital",
                        quantity=Decimal("1"),
                        unit_price_minor=100,
                        line_total_minor=100,
                        fulfillment_status="reserved",
                    )
                )
                await session.flush()
                session.add(
                    DigitalAsset(
                        tenant_id=tenant_a_id,
                        variant_id=variant_id,
                        order_item_id=order_item_id,
                        ciphertext=b"test-ciphertext",
                        idempotency_key=f"asset-{tenant_a_id.hex}",
                        status="reserved",
                    )
                )

        async with session_factory() as session:
            async with session.begin():
                await set_rls_context(session, user_id=str(user_a_id), tenant_id=str(tenant_a_id))
                bypass_rls, is_superuser = (
                    await session.execute(
                        text("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname = current_user")
                    )
                ).one()
                assert bypass_rls is False
                assert is_superuser is False
                rls_tables = {
                    "categories",
                    "products",
                    "product_variants",
                    "warehouses",
                    "inventory_balances",
                    "stock_reservations",
                    "stock_movements",
                    "customers",
                    "customer_addresses",
                    "carts",
                    "cart_items",
                    "orders",
                    "order_items",
                    "payment_attempts",
                    "digital_assets",
                }
                policies = (
                    await session.execute(
                        text(
                            "SELECT relname, relrowsecurity, relforcerowsecurity "
                            "FROM pg_class WHERE relname IN ("
                            "'categories', 'products', 'product_variants', 'warehouses', "
                            "'inventory_balances', 'stock_reservations', 'stock_movements', "
                            "'customers', 'customer_addresses', 'carts', 'cart_items', "
                            "'orders', 'order_items', 'payment_attempts', 'digital_assets')"
                        )
                    )
                ).all()
                assert {row.relname for row in policies} == rls_tables
                assert all(row.relrowsecurity and row.relforcerowsecurity for row in policies)
                visible_tenant_ids = set((await session.scalars(select(Tenant.id))).all())
                visible_memberships = list((await session.scalars(select(TenantMembership))).all())
                assert visible_tenant_ids == {tenant_a_id}
                assert len(visible_memberships) == 1
                assert visible_memberships[0].tenant_id == tenant_a_id
                assert visible_memberships[0].user_id == user_a_id
                assert (await session.scalar(select(Order.id))) == order_id
                assert (await session.scalar(select(DigitalAsset.id))) is not None

        async with session_factory() as session:
            async with session.begin():
                await set_rls_context(session, user_id=str(user_b_id), tenant_id=str(tenant_b_id))
                assert list((await session.scalars(select(Order.id))).all()) == []
                assert list((await session.scalars(select(DigitalAsset.id))).all()) == []

        async with session_factory() as session:
            async with session.begin():
                assert list((await session.scalars(select(Tenant.id))).all()) == []

        async with session_factory() as session:
            async with session.begin():
                await set_rls_context(session, user_id=str(user_a_id), tenant_id=str(tenant_a_id))
                await session.execute(delete(DigitalAsset).where(DigitalAsset.tenant_id == tenant_a_id))
                await session.execute(delete(OrderItem).where(OrderItem.tenant_id == tenant_a_id))
                await session.execute(delete(Order).where(Order.tenant_id == tenant_a_id))
                await session.execute(delete(Customer).where(Customer.tenant_id == tenant_a_id))
                await session.execute(delete(ProductVariant).where(ProductVariant.tenant_id == tenant_a_id))
                await session.execute(delete(Product).where(Product.tenant_id == tenant_a_id))

        for user_id, tenant_id in ((user_a_id, tenant_a_id), (user_b_id, tenant_b_id)):
            async with session_factory() as session:
                async with session.begin():
                    await set_rls_context(session, user_id=str(user_id), tenant_id=str(tenant_id))
                    await session.execute(
                        delete(TenantMembership).where(TenantMembership.tenant_id == tenant_id)
                    )
                    await session.execute(delete(Tenant).where(Tenant.id == tenant_id))

        async with session_factory() as session:
            async with session.begin():
                await session.execute(delete(User).where(User.id.in_([user_a_id, user_b_id])))
    finally:
        await runtime_engine.dispose()