"""Allow paired stock transfer movements."""

from alembic import op

revision = "0003_stock_transfers"
down_revision = "0002_catalog_inventory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_stock_movements_kind", "stock_movements", type_="check")
    op.create_check_constraint(
        "ck_stock_movements_kind",
        "stock_movements",
        "kind IN ('receipt', 'reservation', 'release', 'deduction', 'transfer', 'adjustment', 'return')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_stock_movements_kind", "stock_movements", type_="check")
    op.create_check_constraint(
        "ck_stock_movements_kind",
        "stock_movements",
        "kind IN ('receipt', 'reservation', 'release', 'deduction', 'adjustment', 'return')",
    )