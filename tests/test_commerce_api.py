from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from commerce_api.application import create_app
from commerce_api.core.config import Settings
from commerce_api.db.base import Base
from commerce_api.db.models import DigitalAsset
from commerce_api.db.session import create_engine, create_session_factory
from commerce_api.db.rls import set_rls_context
from commerce_api.schemas import CheckoutRequest
from commerce_api.services.digital_delivery import release_paid_digital_assets
from commerce_api.services.errors import Conflict, PaymentRequired
from commerce_api.services.payments import VerifiedPayment, record_verified_payment


@pytest.fixture
async def api_client(tmp_path) -> AsyncIterator[AsyncClient]:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'commerce-test.db').as_posix()}"
    engine = create_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    settings = Settings(
        _env_file=None,
        database_url=database_url,
        jwt_secret_key="test_secret_key_at_least_32_chars",
        digital_asset_encryption_key=Fernet.generate_key().decode(),
    )
    app = create_app(settings, create_session_factory(engine))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.test_app = app
        yield client
    await engine.dispose()


async def onboard(client: AsyncClient, email: str, slug: str) -> dict:
    response = await client.post(
        "/api/v1/onboarding",
        json={
            "email": email,
            "full_name": f"Owner {slug}",
            "password": "correct-horse-battery-staple",
            "tenant_name": f"Merchant {slug}",
            "tenant_slug": slug,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_two_merchants_are_isolated_through_the_api(api_client: AsyncClient) -> None:
    merchant_a = await onboard(api_client, "owner-a@example.com", "merchant-a")
    merchant_b = await onboard(api_client, "owner-b@example.com", "merchant-b")
    tenant_a = merchant_a["tenant"]["id"]
    tenant_b = merchant_b["tenant"]["id"]
    headers_a = {"Authorization": f"Bearer {merchant_a['access_token']}", "X-Tenant-ID": tenant_a}
    headers_b = {"Authorization": f"Bearer {merchant_b['access_token']}", "X-Tenant-ID": tenant_b}

    own_a = await api_client.get(f"/api/v1/tenants/{tenant_a}", headers=headers_a)
    own_b = await api_client.get(f"/api/v1/tenants/{tenant_b}", headers=headers_b)
    assert own_a.status_code == own_b.status_code == 200
    assert own_a.json()["name"] == "Merchant merchant-a"
    assert own_b.json()["name"] == "Merchant merchant-b"

    cross_read = await api_client.get(f"/api/v1/tenants/{tenant_b}", headers=headers_a)
    cross_write = await api_client.patch(
        f"/api/v1/tenants/{tenant_b}", headers=headers_a, json={"name": "stolen"}
    )
    forged_tenant = await api_client.get(f"/api/v1/tenants/{tenant_b}", headers={
        "Authorization": f"Bearer {merchant_a['access_token']}", "X-Tenant-ID": tenant_b
    })
    assert cross_read.status_code == cross_write.status_code == 404
    assert forged_tenant.status_code == 403

    unchanged_b = await api_client.get(f"/api/v1/tenants/{tenant_b}", headers=headers_b)
    assert unchanged_b.json()["name"] == "Merchant merchant-b"


@pytest.mark.asyncio
async def test_refresh_tokens_rotate_and_cannot_be_replayed(api_client: AsyncClient) -> None:
    merchant = await onboard(api_client, "rotate@example.com", "rotate-shop")
    old_refresh = merchant["refresh_token"]

    first_rotation = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    replay = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})

    assert first_rotation.status_code == 200
    assert first_rotation.json()["refresh_token"] != old_refresh
    assert replay.status_code == 401


@pytest.mark.asyncio
async def test_onboarding_rejects_duplicate_tenant_slug(api_client: AsyncClient) -> None:
    await onboard(api_client, "first@example.com", "shared-slug")
    duplicate = await api_client.post(
        "/api/v1/onboarding",
        json={
            "email": "second@example.com",
            "full_name": "Second Owner",
            "password": "correct-horse-battery-staple",
            "tenant_name": "Second Merchant",
            "tenant_slug": "shared-slug",
        },
    )
    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_tenant_roles_control_member_and_store_management(api_client: AsyncClient) -> None:
    owner = await onboard(api_client, "owner-rbac@example.com", "rbac-shop")
    tenant_id = owner["tenant"]["id"]
    staff_registration = await api_client.post(
        "/api/v1/auth/register",
        json={
            "email": "staff@example.com",
            "full_name": "Shop Staff",
            "password": "correct-horse-battery-staple",
        },
    )
    assert staff_registration.status_code == 201
    owner_headers = {
        "Authorization": f"Bearer {owner['access_token']}",
        "X-Tenant-ID": tenant_id,
    }
    added = await api_client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        headers=owner_headers,
        json={"email": "staff@example.com", "role": "staff"},
    )
    assert added.status_code == 201
    assert added.json()["role"] == "staff"

    staff_login = await api_client.post(
        "/api/v1/auth/login",
        json={
            "email": "staff@example.com",
            "password": "correct-horse-battery-staple",
            "tenant_id": tenant_id,
        },
    )
    assert staff_login.status_code == 200
    staff_headers = {
        "Authorization": f"Bearer {staff_login.json()['access_token']}",
        "X-Tenant-ID": tenant_id,
    }
    assert (await api_client.get(f"/api/v1/tenants/{tenant_id}/members", headers=staff_headers)).status_code == 200
    staff_update = await api_client.patch(
        f"/api/v1/tenants/{tenant_id}", headers=staff_headers, json={"name": "unauthorized"}
    )
    assert staff_update.status_code == 403

    promoted = await api_client.patch(
        f"/api/v1/tenants/{tenant_id}/members/{staff_registration.json()['id']}",
        headers=owner_headers,
        json={"role": "admin"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"
    admin_update = await api_client.patch(
        f"/api/v1/tenants/{tenant_id}", headers=staff_headers, json={"name": "Managed by admin"}
    )
    assert admin_update.status_code == 200


@pytest.mark.asyncio
async def test_catalog_stock_receipts_and_reservations_are_tenant_scoped(
    api_client: AsyncClient,
) -> None:
    merchant = await onboard(api_client, "inventory@example.com", "inventory-shop")
    tenant_id = merchant["tenant"]["id"]
    headers = {
        "Authorization": f"Bearer {merchant['access_token']}",
        "X-Tenant-ID": tenant_id,
    }
    category_response = await api_client.post(
        "/api/v1/catalog/categories", headers=headers, json={"name": "Tools", "slug": "tools"}
    )
    assert category_response.status_code == 201
    product_response = await api_client.post(
        "/api/v1/catalog/products",
        headers=headers,
        json={
            "category_id": category_response.json()["id"],
            "name": "Widget",
            "slug": "widget",
            "unit_price_minor": 1250,
        },
    )
    assert product_response.status_code == 201
    published_product = await api_client.patch(
        f"/api/v1/catalog/products/{product_response.json()['id']}",
        headers=headers,
        json={"is_active": True},
    )
    assert published_product.status_code == 200
    assert published_product.json()["is_active"] is True
    variant_response = await api_client.post(
        f"/api/v1/catalog/products/{product_response.json()['id']}/variants",
        headers=headers,
        json={"name": "Standard", "sku": "widget-std"},
    )
    warehouse_response = await api_client.post(
        "/api/v1/warehouses", headers=headers, json={"name": "Main", "code": "main"}
    )
    assert variant_response.status_code == warehouse_response.status_code == 201
    variant_id = variant_response.json()["id"]
    warehouse_id = warehouse_response.json()["id"]

    configured = await api_client.put(
        "/api/v1/inventory/balances",
        headers=headers,
        json={"variant_id": variant_id, "warehouse_id": warehouse_id, "safety_stock": "1"},
    )
    assert configured.status_code == 200
    receipt_values = {
        "variant_id": variant_id,
        "warehouse_id": warehouse_id,
        "quantity": "2",
        "idempotency_key": "initial-receipt",
        "reason": "opening stock",
    }
    first_receipt = await api_client.post("/api/v1/inventory/receipts", headers=headers, json=receipt_values)
    replay_receipt = await api_client.post("/api/v1/inventory/receipts", headers=headers, json=receipt_values)
    assert first_receipt.status_code == replay_receipt.status_code == 201
    assert replay_receipt.json()["balance"]["on_hand"] == "2.000"
    assert replay_receipt.json()["balance"]["available"] == "1.000"

    reserve_values = {
        "variant_id": variant_id,
        "warehouse_id": warehouse_id,
        "quantity": "1",
        "idempotency_key": "checkout-a",
    }
    reservation = await api_client.post("/api/v1/inventory/reservations", headers=headers, json=reserve_values)
    replay_reservation = await api_client.post(
        "/api/v1/inventory/reservations", headers=headers, json=reserve_values
    )
    assert reservation.status_code == replay_reservation.status_code == 201
    assert reservation.json()["id"] == replay_reservation.json()["id"]
    out_of_stock = await api_client.post(
        "/api/v1/inventory/reservations",
        headers=headers,
        json={**reserve_values, "idempotency_key": "checkout-b", "quantity": "0.001"},
    )
    assert out_of_stock.status_code == 409

    released = await api_client.post(
        f"/api/v1/inventory/reservations/{reservation.json()['id']}/release", headers=headers
    )
    assert released.status_code == 200
    assert released.json()["status"] == "released"

    second_reservation = await api_client.post(
        "/api/v1/inventory/reservations",
        headers=headers,
        json={**reserve_values, "idempotency_key": "checkout-c"},
    )
    deducted = await api_client.post(
        f"/api/v1/inventory/reservations/{second_reservation.json()['id']}/deduct", headers=headers
    )
    assert deducted.status_code == 200
    assert deducted.json()["status"] == "deducted"
    balance = await api_client.get(
        f"/api/v1/inventory/balances/{warehouse_id}/{variant_id}", headers=headers
    )
    assert balance.json()["on_hand"] == "1.000"
    assert balance.json()["reserved"] == "0.000"
    assert balance.json()["available"] == "0.000"

    returned = await api_client.post(
        "/api/v1/inventory/returns",
        headers=headers,
        json={
            "variant_id": variant_id,
            "warehouse_id": warehouse_id,
            "quantity": "1",
            "idempotency_key": "customer-return-1",
            "reason": "unopened return",
        },
    )
    assert returned.status_code == 201
    destination_warehouse = await api_client.post(
        "/api/v1/warehouses", headers=headers, json={"name": "Overflow", "code": "overflow"}
    )
    transfer_values = {
        "variant_id": variant_id,
        "source_warehouse_id": warehouse_id,
        "destination_warehouse_id": destination_warehouse.json()["id"],
        "quantity": "0.5",
        "idempotency_key": "transfer-batch-1",
    }
    transfer = await api_client.post("/api/v1/inventory/transfers", headers=headers, json=transfer_values)
    transfer_replay = await api_client.post(
        "/api/v1/inventory/transfers", headers=headers, json=transfer_values
    )
    assert transfer.status_code == transfer_replay.status_code == 201
    assert transfer.json()["source"]["on_hand"] == "1.500"
    assert transfer.json()["destination"]["on_hand"] == "0.500"
    assert transfer_replay.json()["source"]["on_hand"] == transfer.json()["source"]["on_hand"]
    assert transfer_replay.json()["destination"]["on_hand"] == transfer.json()["destination"]["on_hand"]

    blocked_adjustment = await api_client.post(
        "/api/v1/inventory/adjustments",
        headers=headers,
        json={
            "variant_id": variant_id,
            "warehouse_id": warehouse_id,
            "delta": "-0.6",
            "idempotency_key": "adjust-down-too-far",
            "reason": "damaged units",
        },
    )
    assert blocked_adjustment.status_code == 409
    adjusted = await api_client.post(
        "/api/v1/inventory/adjustments",
        headers=headers,
        json={
            "variant_id": variant_id,
            "warehouse_id": warehouse_id,
            "delta": "0.25",
            "idempotency_key": "adjust-up",
            "reason": "count correction",
        },
    )
    assert adjusted.status_code == 201
    assert adjusted.json()["balance"]["on_hand"] == "1.750"

    other_merchant = await onboard(api_client, "inventory-other@example.com", "other-shop")
    other_headers = {
        "Authorization": f"Bearer {other_merchant['access_token']}",
        "X-Tenant-ID": other_merchant["tenant"]["id"],
    }
    foreign_product = await api_client.post(
        "/api/v1/catalog/products",
        headers=other_headers,
        json={
            "category_id": category_response.json()["id"],
            "name": "Cross Tenant",
            "slug": "cross-tenant",
            "unit_price_minor": 100,
        },
    )
    assert foreign_product.status_code == 404


@pytest.mark.asyncio
async def test_physical_checkout_reserves_stock_and_keeps_immutable_snapshots(
    api_client: AsyncClient,
) -> None:
    merchant = await onboard(api_client, "orders@example.com", "orders-shop")
    tenant_id = merchant["tenant"]["id"]
    headers = {"Authorization": f"Bearer {merchant['access_token']}", "X-Tenant-ID": tenant_id}
    category = await api_client.post(
        "/api/v1/catalog/categories", headers=headers, json={"name": "Goods", "slug": "goods"}
    )
    product = await api_client.post(
        "/api/v1/catalog/products",
        headers=headers,
        json={
            "category_id": category.json()["id"],
            "name": "Ceramic Cup",
            "slug": "cup",
            "unit_price_minor": 700,
            "is_active": True,
        },
    )
    variant = await api_client.post(
        f"/api/v1/catalog/products/{product.json()['id']}/variants",
        headers=headers,
        json={"name": "Blue", "sku": "CUP-BLUE"},
    )
    warehouse = await api_client.post(
        "/api/v1/warehouses", headers=headers, json={"name": "Main", "code": "orders"}
    )
    receipt = await api_client.post(
        "/api/v1/inventory/receipts",
        headers=headers,
        json={
            "variant_id": variant.json()["id"],
            "warehouse_id": warehouse.json()["id"],
            "quantity": "5",
            "idempotency_key": "orders-seed-stock",
        },
    )
    assert receipt.status_code == 201

    customer = await api_client.post(
        "/api/v1/customers",
        headers=headers,
        json={"full_name": "Order Customer", "email": "buyer@example.com"},
    )
    address = await api_client.post(
        f"/api/v1/customers/{customer.json()['id']}/addresses",
        headers=headers,
        json={
            "recipient_name": "Order Customer",
            "phone": "+15550001111",
            "address": {"line1": "1 Main Street", "city": "Springfield", "country": "US"},
        },
    )
    cart = await api_client.post("/api/v1/carts", headers=headers, json={"customer_id": customer.json()["id"]})
    await api_client.post(
        f"/api/v1/carts/{cart.json()['id']}/items",
        headers=headers,
        json={"variant_id": variant.json()["id"], "quantity": "2"},
    )
    checkout = await api_client.post(
        f"/api/v1/carts/{cart.json()['id']}/checkout",
        headers=headers,
        json={
            "checkout_key": "physical-checkout-1",
            "warehouse_id": warehouse.json()["id"],
            "shipping_address_id": address.json()["id"],
        },
    )
    assert checkout.status_code == 201, checkout.text
    order = checkout.json()
    assert order["payment_status"] == "pending"
    assert order["fulfillment_status"] == "reserved"
    assert order["total_minor"] == 1400
    assert order["shipping_address_snapshot"]["line1"] == "1 Main Street"
    assert order["items"][0]["product_name_snapshot"] == "Ceramic Cup"
    assert order["items"][0]["unit_price_minor"] == 700
    assert order["items"][0]["stock_reservation_id"]

    await api_client.patch(
        f"/api/v1/catalog/products/{product.json()['id']}",
        headers=headers,
        json={"name": "Updated Cup", "unit_price_minor": 900},
    )
    history = await api_client.get(f"/api/v1/orders/{order['id']}", headers=headers)
    assert history.json()["items"][0]["product_name_snapshot"] == "Ceramic Cup"
    assert history.json()["items"][0]["unit_price_minor"] == 700


@pytest.mark.asyncio
async def test_digital_assets_are_encrypted_and_payment_gated(api_client: AsyncClient) -> None:
    merchant = await onboard(api_client, "digital@example.com", "digital-shop")
    tenant_id = merchant["tenant"]["id"]
    headers = {"Authorization": f"Bearer {merchant['access_token']}", "X-Tenant-ID": tenant_id}
    category = await api_client.post(
        "/api/v1/catalog/categories", headers=headers, json={"name": "Codes", "slug": "codes"}
    )
    product = await api_client.post(
        "/api/v1/catalog/products",
        headers=headers,
        json={
            "category_id": category.json()["id"],
            "name": "Game Code",
            "slug": "game-code",
            "unit_price_minor": 500,
            "product_type": "digital",
            "is_active": True,
        },
    )
    assert product.status_code == 201
    variant = await api_client.post(
        f"/api/v1/catalog/products/{product.json()['id']}/variants",
        headers=headers,
        json={"name": "Global", "sku": "GAME-GLOBAL"},
    )
    secret_asset = "REDEEM-THIS-SECRET-CODE"
    stocked = await api_client.post(
        f"/api/v1/catalog/variants/{variant.json()['id']}/digital-assets",
        headers=headers,
        json={"asset": secret_asset, "idempotency_key": "digital-asset-1"},
    )
    assert stocked.status_code == 201, stocked.text
    assert secret_asset not in stocked.text
    async with api_client.test_app.state.session_factory() as session:
        stored_asset = await session.get(DigitalAsset, UUID(stocked.json()["id"]))
        assert stored_asset is not None
        assert secret_asset.encode() not in stored_asset.ciphertext

    customer = await api_client.post(
        "/api/v1/customers", headers=headers, json={"full_name": "Digital Buyer"}
    )
    cart = await api_client.post("/api/v1/carts", headers=headers, json={"customer_id": customer.json()["id"]})
    await api_client.post(
        f"/api/v1/carts/{cart.json()['id']}/items",
        headers=headers,
        json={"variant_id": variant.json()["id"], "quantity": "1"},
    )
    checkout = await api_client.post(
        f"/api/v1/carts/{cart.json()['id']}/checkout",
        headers=headers,
        json={"checkout_key": "digital-checkout-1"},
    )
    assert checkout.status_code == 201, checkout.text
    order_id = checkout.json()["id"]
    assert checkout.json()["payment_status"] == "pending"
    assert checkout.json()["items"][0]["product_type"] == "digital"
    api_paths = api_client.test_app.openapi()["paths"]
    assert not any("/payments" in path or "digital-delivery" in path for path in api_paths)

    checkout_replay = await api_client.post(
        f"/api/v1/carts/{cart.json()['id']}/checkout",
        headers=headers,
        json={"checkout_key": "digital-checkout-1"},
    )
    assert checkout_replay.status_code == 201
    assert checkout_replay.json()["id"] == order_id

    settings = api_client.test_app.state.settings
    session_factory = api_client.test_app.state.session_factory
    async with session_factory() as session:
        async with session.begin():
            await set_rls_context(
                session, user_id=merchant["user"]["id"], tenant_id=tenant_id
            )
            with pytest.raises(PaymentRequired):
                await release_paid_digital_assets(
                    session,
                    tenant_id=UUID(tenant_id),
                    order_id=UUID(order_id),
                    settings=settings,
                )

    async with session_factory() as session:
        async with session.begin():
            await set_rls_context(
                session, user_id=merchant["user"]["id"], tenant_id=tenant_id
            )
            with pytest.raises(Conflict):
                await record_verified_payment(
                    session,
                    VerifiedPayment(
                        tenant_id=UUID(tenant_id),
                        order_id=UUID(order_id),
                        provider="test-provider",
                        provider_reference="wrong-amount-reference",
                        amount_minor=499,
                        currency="USD",
                        verified_at=datetime.now(UTC),
                    ),
                )
            paid_order = await record_verified_payment(
                session,
                VerifiedPayment(
                    tenant_id=UUID(tenant_id),
                    order_id=UUID(order_id),
                    provider="test-provider",
                    provider_reference="verified-reference-1",
                    amount_minor=500,
                    currency="USD",
                    verified_at=datetime.now(UTC),
                ),
            )
            assert paid_order.payment_status == "paid"

    async with session_factory() as session:
        async with session.begin():
            await set_rls_context(
                session, user_id=merchant["user"]["id"], tenant_id=tenant_id
            )
            delivered = await release_paid_digital_assets(
                session,
                tenant_id=UUID(tenant_id),
                order_id=UUID(order_id),
                settings=settings,
            )
            assert [item.asset for item in delivered] == [secret_asset]

    async with session_factory() as session:
        async with session.begin():
            await set_rls_context(session, user_id=merchant["user"]["id"], tenant_id=tenant_id)
            replayed_delivery = await release_paid_digital_assets(
                session,
                tenant_id=UUID(tenant_id),
                order_id=UUID(order_id),
                settings=settings,
            )
            assert [item.asset for item in replayed_delivery] == [secret_asset]
