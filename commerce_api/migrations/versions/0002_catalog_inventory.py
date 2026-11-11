"""Tenant-scoped catalog and inventory foundation."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from commerce_api.db.rls import tenant_rls_statements

revision = "0002_catalog_inventory"
down_revision = "0001_sprint1_tenancy"
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "categories",
    "products",
    "product_variants",
    "warehouses",
    "inventory_balances",
    "stock_reservations",
    "stock_movements",
)


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_categories_tenant_id"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_categories_tenant_slug"),
    )
    op.create_index("ix_categories_tenant_id", "categories", ["tenant_id"])

    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("unit_price_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_products_tenant_id"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_products_tenant_slug"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "category_id"], ["categories.tenant_id", "categories.id"],
            name="fk_products_tenant_category", ondelete="RESTRICT",
        ),
        sa.CheckConstraint("unit_price_minor >= 0", name="ck_products_price_nonnegative"),
    )
    op.create_index("ix_products_tenant_active", "products", ["tenant_id", "is_active"])

    op.create_table(
        "product_variants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("sku", sa.String(length=80), nullable=False),
        sa.Column("price_minor", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_variants_tenant_id"),
        sa.UniqueConstraint("tenant_id", "sku", name="uq_variants_tenant_sku"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"], ["products.tenant_id", "products.id"],
            name="fk_variants_tenant_product", ondelete="CASCADE",
        ),
        sa.CheckConstraint("price_minor IS NULL OR price_minor >= 0", name="ck_variants_price_nonnegative"),
    )

    op.create_table(
        "warehouses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_warehouses_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_warehouses_tenant_code"),
    )
    op.create_index("ix_warehouses_tenant_id", "warehouses", ["tenant_id"])

    op.create_table(
        "inventory_balances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("warehouse_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("on_hand", sa.Numeric(18, 3), nullable=False),
        sa.Column("reserved", sa.Numeric(18, 3), nullable=False),
        sa.Column("safety_stock", sa.Numeric(18, 3), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "variant_id", "warehouse_id", name="uq_inventory_balance_location"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "variant_id"], ["product_variants.tenant_id", "product_variants.id"],
            name="fk_inventory_balance_tenant_variant", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"], ["warehouses.tenant_id", "warehouses.id"],
            name="fk_inventory_balance_tenant_warehouse", ondelete="CASCADE",
        ),
        sa.CheckConstraint("on_hand >= 0", name="ck_inventory_on_hand_nonnegative"),
        sa.CheckConstraint("reserved >= 0", name="ck_inventory_reserved_nonnegative"),
        sa.CheckConstraint("safety_stock >= 0", name="ck_inventory_safety_stock_nonnegative"),
        sa.CheckConstraint("reserved <= on_hand", name="ck_inventory_reserved_lte_on_hand"),
    )

    op.create_table(
        "stock_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("warehouse_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "id", name="uq_reservations_tenant_id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_reservations_tenant_idempotency"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "variant_id"], ["product_variants.tenant_id", "product_variants.id"],
            name="fk_reservations_tenant_variant", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"], ["warehouses.tenant_id", "warehouses.id"],
            name="fk_reservations_tenant_warehouse", ondelete="CASCADE",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_reservations_quantity_positive"),
        sa.CheckConstraint("status IN ('active', 'released', 'expired', 'deducted')", name="ck_reservations_status"),
    )
    op.create_index("ix_reservations_expiry", "stock_reservations", ["tenant_id", "status", "expires_at"])

    op.create_table(
        "stock_movements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("warehouse_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=240), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_stock_movements_tenant_idempotency"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "variant_id"], ["product_variants.tenant_id", "product_variants.id"],
            name="fk_stock_movements_tenant_variant", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"], ["warehouses.tenant_id", "warehouses.id"],
            name="fk_stock_movements_tenant_warehouse", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reservation_id"], ["stock_reservations.tenant_id", "stock_reservations.id"],
            name="fk_stock_movements_tenant_reservation", ondelete="CASCADE",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_stock_movements_quantity_positive"),
        sa.CheckConstraint(
            "kind IN ('receipt', 'reservation', 'release', 'deduction', 'adjustment', 'return')",
            name="ck_stock_movements_kind",
        ),
    )
    op.create_index("ix_stock_movements_tenant_variant_created", "stock_movements", ["tenant_id", "variant_id", "created_at"])

    for statement in tenant_rls_statements(TENANT_TABLES):
        op.execute(statement)


def downgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_stock_movements_tenant_variant_created", table_name="stock_movements")
    op.drop_table("stock_movements")
    op.drop_index("ix_reservations_expiry", table_name="stock_reservations")
    op.drop_table("stock_reservations")
    op.drop_table("inventory_balances")
    op.drop_index("ix_warehouses_tenant_id", table_name="warehouses")
    op.drop_table("warehouses")
    op.drop_table("product_variants")
    op.drop_index("ix_products_tenant_active", table_name="products")
    op.drop_table("products")
    op.drop_index("ix_categories_tenant_id", table_name="categories")
    op.drop_table("categories")