from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    JSON,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from commerce_api.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class MembershipRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    STAFF = "staff"


class ReservationStatus(StrEnum):
    ACTIVE = "active"
    RELEASED = "released"
    EXPIRED = "expired"
    DEDUCTED = "deducted"


class ProductType(StrEnum):
    PHYSICAL = "physical"
    DIGITAL = "digital"


class CartStatus(StrEnum):
    ACTIVE = "active"
    CHECKED_OUT = "checked_out"
    ABANDONED = "abandoned"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class FulfillmentStatus(StrEnum):
    UNFULFILLED = "unfulfilled"
    RESERVED = "reserved"
    PROCESSING = "processing"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


class DigitalAssetStatus(StrEnum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    DELIVERED = "delivered"


class StockMovementKind(StrEnum):
    RECEIPT = "receipt"
    RESERVATION = "reservation"
    RELEASE = "release"
    DEDUCTION = "deduction"
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"
    RETURN = "return"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_email", "email", unique=True),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class TenantMembership(Base):
    __tablename__ = "tenant_memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_memberships_tenant_user"),
        CheckConstraint("role IN ('owner', 'admin', 'staff')", name="ck_tenant_memberships_role"),
        Index("ix_tenant_memberships_user", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=MembershipRole.STAFF)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"
    __table_args__ = (Index("ix_refresh_sessions_user", "user_id"),)

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_categories_tenant_id"),
        UniqueConstraint("tenant_id", "slug", name="uq_categories_tenant_slug"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_products_tenant_id"),
        UniqueConstraint("tenant_id", "slug", name="uq_products_tenant_slug"),
        ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["categories.tenant_id", "categories.id"],
            name="fk_products_tenant_category",
            ondelete="RESTRICT",
        ),
        CheckConstraint("unit_price_minor >= 0", name="ck_products_price_nonnegative"),
        CheckConstraint("product_type IN ('physical', 'digital')", name="ck_products_product_type"),
        Index("ix_products_tenant_active", "tenant_id", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    unit_price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    product_type: Mapped[str] = mapped_column(String(16), nullable=False, default=ProductType.PHYSICAL)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ProductVariant(Base):
    __tablename__ = "product_variants"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_variants_tenant_id"),
        UniqueConstraint("tenant_id", "sku", name="uq_variants_tenant_sku"),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_variants_tenant_product",
            ondelete="CASCADE",
        ),
        CheckConstraint("price_minor IS NULL OR price_minor >= 0", name="ck_variants_price_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    sku: Mapped[str] = mapped_column(String(80), nullable=False)
    price_minor: Mapped[int | None] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class Warehouse(Base):
    __tablename__ = "warehouses"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_warehouses_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_warehouses_tenant_code"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class InventoryBalance(Base):
    __tablename__ = "inventory_balances"
    __table_args__ = (
        UniqueConstraint("tenant_id", "variant_id", "warehouse_id", name="uq_inventory_balance_location"),
        ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["product_variants.tenant_id", "product_variants.id"],
            name="fk_inventory_balance_tenant_variant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_inventory_balance_tenant_warehouse",
            ondelete="CASCADE",
        ),
        CheckConstraint("on_hand >= 0", name="ck_inventory_on_hand_nonnegative"),
        CheckConstraint("reserved >= 0", name="ck_inventory_reserved_nonnegative"),
        CheckConstraint("safety_stock >= 0", name="ck_inventory_safety_stock_nonnegative"),
        CheckConstraint("reserved <= on_hand", name="ck_inventory_reserved_lte_on_hand"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    variant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    warehouse_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    on_hand: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0"))
    reserved: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0"))
    safety_stock: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class StockReservation(Base):
    __tablename__ = "stock_reservations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_reservations_tenant_id"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_reservations_tenant_idempotency"),
        ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["product_variants.tenant_id", "product_variants.id"],
            name="fk_reservations_tenant_variant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_reservations_tenant_warehouse",
            ondelete="CASCADE",
        ),
        CheckConstraint("quantity > 0", name="ck_reservations_quantity_positive"),
        CheckConstraint(
            "status IN ('active', 'released', 'expired', 'deducted')", name="ck_reservations_status"
        ),
        Index("ix_reservations_expiry", "tenant_id", "status", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    variant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    warehouse_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=ReservationStatus.ACTIVE)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_stock_movements_tenant_idempotency"),
        ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["product_variants.tenant_id", "product_variants.id"],
            name="fk_stock_movements_tenant_variant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_stock_movements_tenant_warehouse",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "reservation_id"],
            ["stock_reservations.tenant_id", "stock_reservations.id"],
            name="fk_stock_movements_tenant_reservation",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        CheckConstraint("quantity > 0", name="ck_stock_movements_quantity_positive"),
        CheckConstraint(
            "kind IN ('receipt', 'reservation', 'release', 'deduction', 'transfer', 'adjustment', 'return')",
            name="ck_stock_movements_kind",
        ),
        Index("ix_stock_movements_tenant_variant_created", "tenant_id", "variant_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    variant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    warehouse_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    reservation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    actor_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_customers_tenant_id"),
        UniqueConstraint("tenant_id", "email", name="uq_customers_tenant_email"),
        Index("ix_customers_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class CustomerAddress(Base):
    __tablename__ = "customer_addresses"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_customer_addresses_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name="fk_customer_addresses_tenant_customer",
            ondelete="CASCADE",
        ),
        Index("ix_customer_addresses_tenant_customer", "tenant_id", "customer_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    recipient_name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    address: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class Cart(Base):
    __tablename__ = "carts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_carts_tenant_id"),
        UniqueConstraint("tenant_id", "checkout_key", name="uq_carts_tenant_checkout_key"),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name="fk_carts_tenant_customer",
            ondelete="CASCADE",
        ),
        CheckConstraint("status IN ('active', 'checked_out', 'abandoned')", name="ck_carts_status"),
        Index("ix_carts_tenant_customer_status", "tenant_id", "customer_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=CartStatus.ACTIVE)
    checkout_key: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "cart_id", "variant_id", name="uq_cart_items_variant"),
        ForeignKeyConstraint(
            ["tenant_id", "cart_id"], ["carts.tenant_id", "carts.id"],
            name="fk_cart_items_tenant_cart", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "variant_id"], ["product_variants.tenant_id", "product_variants.id"],
            name="fk_cart_items_tenant_variant", ondelete="CASCADE",
        ),
        CheckConstraint("quantity > 0", name="ck_cart_items_quantity_positive"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    cart_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    variant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_orders_tenant_id"),
        UniqueConstraint("tenant_id", "checkout_key", name="uq_orders_tenant_checkout_key"),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"], ["customers.tenant_id", "customers.id"],
            name="fk_orders_tenant_customer", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "shipping_address_id"], ["customer_addresses.tenant_id", "customer_addresses.id"],
            name="fk_orders_tenant_shipping_address", ondelete="RESTRICT",
        ),
        CheckConstraint("payment_status IN ('pending', 'paid', 'failed', 'refunded')", name="ck_orders_payment_status"),
        CheckConstraint(
            "fulfillment_status IN ('unfulfilled', 'reserved', 'processing', 'fulfilled', 'cancelled')",
            name="ck_orders_fulfillment_status",
        ),
        CheckConstraint("subtotal_minor >= 0 AND total_minor >= 0", name="ck_orders_totals_nonnegative"),
        Index("ix_orders_tenant_customer_created", "tenant_id", "customer_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    shipping_address_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    shipping_address_snapshot: Mapped[dict | None] = mapped_column(JSON)
    checkout_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="api")
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payment_status: Mapped[str] = mapped_column(String(16), nullable=False, default=PaymentStatus.PENDING)
    fulfillment_status: Mapped[str] = mapped_column(String(20), nullable=False, default=FulfillmentStatus.RESERVED)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_order_items_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "order_id"], ["orders.tenant_id", "orders.id"],
            name="fk_order_items_tenant_order", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "variant_id"], ["product_variants.tenant_id", "product_variants.id"],
            name="fk_order_items_tenant_variant", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "stock_reservation_id"], ["stock_reservations.tenant_id", "stock_reservations.id"],
            name="fk_order_items_tenant_reservation", ondelete="RESTRICT",
        ),
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        CheckConstraint("unit_price_minor >= 0 AND line_total_minor >= 0", name="ck_order_items_amounts_nonnegative"),
        CheckConstraint("product_type IN ('physical', 'digital')", name="ck_order_items_product_type"),
        CheckConstraint(
            "fulfillment_status IN ('unfulfilled', 'reserved', 'processing', 'fulfilled', 'cancelled')",
            name="ck_order_items_fulfillment_status",
        ),
        Index("ix_order_items_tenant_order", "tenant_id", "order_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    order_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    variant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    stock_reservation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    product_name_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    variant_name_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    sku_snapshot: Mapped[str] = mapped_column(String(80), nullable=False)
    product_type: Mapped[str] = mapped_column(String(16), nullable=False)
    fulfillment_status: Mapped[str] = mapped_column(String(20), nullable=False, default=FulfillmentStatus.RESERVED)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    line_total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class PaymentAttempt(Base):
    __tablename__ = "payment_attempts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_payment_attempts_tenant_id"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_payment_attempts_tenant_idempotency"),
        UniqueConstraint("tenant_id", "provider", "provider_reference", name="uq_payment_attempts_provider_reference"),
        ForeignKeyConstraint(
            ["tenant_id", "order_id"], ["orders.tenant_id", "orders.id"],
            name="fk_payment_attempts_tenant_order", ondelete="CASCADE",
        ),
        CheckConstraint("amount_minor >= 0", name="ck_payment_attempts_amount_nonnegative"),
        CheckConstraint("status IN ('pending', 'paid', 'failed', 'refunded')", name="ck_payment_attempts_status"),
        Index("ix_payment_attempts_tenant_order", "tenant_id", "order_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    order_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(160))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=PaymentStatus.PENDING)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class DigitalAsset(Base):
    __tablename__ = "digital_assets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_digital_assets_tenant_id"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_digital_assets_tenant_idempotency"),
        ForeignKeyConstraint(
            ["tenant_id", "variant_id"], ["product_variants.tenant_id", "product_variants.id"],
            name="fk_digital_assets_tenant_variant", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "order_item_id"], ["order_items.tenant_id", "order_items.id"],
            name="fk_digital_assets_tenant_order_item", ondelete="RESTRICT",
        ),
        CheckConstraint("status IN ('available', 'reserved', 'delivered')", name="ck_digital_assets_status"),
        Index("ix_digital_assets_tenant_variant_status", "tenant_id", "variant_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    variant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    order_item_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=DigitalAssetStatus.AVAILABLE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))