from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

RLS_POLICIES = {
    "tenants": (
        "id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
        "OR current_setting('app.is_platform_admin', true) = 'true'"
    ),
    "tenant_memberships": (
        "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
    ),
    "categories": "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid",
    "products": "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid",
    "product_variants": "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid",
    "warehouses": "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid",
    "inventory_balances": "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid",
    "stock_reservations": "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid",
    "stock_movements": "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid",
    "customers": "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid",
    "customer_addresses": "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid",
    "carts": "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid",
    "cart_items": "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid",
    "orders": "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid",
    "order_items": "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid",
    "payment_attempts": "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid",
    "digital_assets": "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid",
}


def tenant_rls_statements(tables: tuple[str, ...] | None = None) -> list[str]:
    statements: list[str] = []
    for table in tables or tuple(RLS_POLICIES):
        predicate = RLS_POLICIES[table]
        policy_name = f"{table}_tenant_isolation"
        statements.extend(
            [
                f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
                f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
                f"CREATE POLICY {policy_name} ON {table} USING ({predicate}) WITH CHECK ({predicate})",
            ]
        )
    return statements


async def set_rls_context(
    session: AsyncSession, *, user_id: str, tenant_id: str, is_platform_admin: bool = False
) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    await session.execute(
        text(
            "SELECT set_config('app.user_id', :user_id, true), "
            "set_config('app.tenant_id', :tenant_id, true), "
            "set_config('app.is_platform_admin', :is_platform_admin, true)"
        ),
        {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "is_platform_admin": "true" if is_platform_admin else "false",
        },
    )