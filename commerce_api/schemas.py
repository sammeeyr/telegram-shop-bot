from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, StringConstraints, field_validator

Slug = Annotated[str, StringConstraints(min_length=3, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    password: SecretStr = Field(min_length=12, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class LoginRequest(BaseModel):
    email: EmailStr
    password: SecretStr
    tenant_id: UUID


class OnboardingRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    password: SecretStr = Field(min_length=12, max_length=256)
    tenant_name: str = Field(min_length=1, max_length=160)
    tenant_slug: Slug

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("full_name", "tenant_name")
    @classmethod
    def strip_nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value


class RefreshRequest(BaseModel):
    refresh_token: SecretStr


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    slug: Slug

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name must not be blank")
        return value


class TenantUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name must not be blank")
        return value


class MembershipCreateRequest(BaseModel):
    email: EmailStr
    role: Literal["admin", "staff"] = "staff"

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class MembershipUpdateRequest(BaseModel):
    role: Literal["admin", "staff"]


class TenantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    created_at: datetime


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str


class MembershipResponse(BaseModel):
    user_id: UUID
    email: EmailStr
    full_name: str
    role: str


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: Annotated[str, StringConstraints(min_length=2, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name must not be blank")
        return value


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime


class ProductCreate(BaseModel):
    category_id: UUID | None = None
    name: str = Field(min_length=1, max_length=160)
    slug: Annotated[str, StringConstraints(min_length=2, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
    description: str = Field(default="", max_length=10000)
    unit_price_minor: int = Field(ge=0, le=9_000_000_000_000_000)
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] = "USD"
    is_active: bool = False
    product_type: Literal["physical", "digital"] = "physical"

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name must not be blank")
        return value


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    category_id: UUID | None
    name: str
    slug: str
    description: str
    unit_price_minor: int
    currency: str
    product_type: str
    is_active: bool
    created_at: datetime


class ProductUpdate(BaseModel):
    category_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=10000)
    unit_price_minor: int | None = Field(default=None, ge=0, le=9_000_000_000_000_000)
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] | None = None
    is_active: bool | None = None
    product_type: Literal["physical", "digital"] | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Name must not be blank")
        return value


class VariantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    sku: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    price_minor: int | None = Field(default=None, ge=0, le=9_000_000_000_000_000)
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name must not be blank")
        return value

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("SKU must not be blank")
        return value


class VariantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    product_id: UUID
    name: str
    sku: str
    price_minor: int | None
    is_active: bool
    created_at: datetime


class WarehouseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    code: Annotated[str, StringConstraints(min_length=1, max_length=40)]

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name must not be blank")
        return value

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("Warehouse code must not be blank")
        return value


class WarehouseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    code: str
    is_active: bool
    created_at: datetime


class StockReceiptRequest(BaseModel):
    variant_id: UUID
    warehouse_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    idempotency_key: str = Field(min_length=1, max_length=128)
    reason: str = Field(default="", max_length=240)

    @field_validator("idempotency_key")
    @classmethod
    def clean_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Idempotency key must not be blank")
        return value


class InventoryBalanceConfigureRequest(BaseModel):
    variant_id: UUID
    warehouse_id: UUID
    safety_stock: Decimal = Field(ge=0, max_digits=18, decimal_places=3)


class InventoryBalanceResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    variant_id: UUID
    warehouse_id: UUID
    on_hand: Decimal
    reserved: Decimal
    available: Decimal
    safety_stock: Decimal
    updated_at: datetime


class StockMovementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    variant_id: UUID
    warehouse_id: UUID
    reservation_id: UUID | None
    actor_user_id: UUID | None
    kind: str
    quantity: Decimal
    idempotency_key: str
    reason: str
    created_at: datetime


class StockReceiptResponse(BaseModel):
    balance: InventoryBalanceResponse
    movement: StockMovementResponse


class StockAdjustmentRequest(BaseModel):
    variant_id: UUID
    warehouse_id: UUID
    delta: Decimal = Field(max_digits=18, decimal_places=3)
    idempotency_key: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=220)

    @field_validator("idempotency_key")
    @classmethod
    def clean_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Idempotency key must not be blank")
        return value

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Reason must not be blank")
        return value


class StockReturnRequest(BaseModel):
    variant_id: UUID
    warehouse_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    idempotency_key: str = Field(min_length=1, max_length=128)
    reason: str = Field(default="", max_length=240)

    @field_validator("idempotency_key")
    @classmethod
    def clean_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Idempotency key must not be blank")
        return value


class StockTransferRequest(BaseModel):
    variant_id: UUID
    source_warehouse_id: UUID
    destination_warehouse_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    idempotency_key: str = Field(min_length=1, max_length=128)
    reason: str = Field(default="", max_length=200)

    @field_validator("idempotency_key")
    @classmethod
    def clean_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Idempotency key must not be blank")
        return value


class StockTransferResponse(BaseModel):
    source: InventoryBalanceResponse
    destination: InventoryBalanceResponse


class ReservationCreateRequest(BaseModel):
    variant_id: UUID
    warehouse_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    idempotency_key: str = Field(min_length=1, max_length=128)
    expires_in_seconds: int = Field(default=900, ge=60, le=604800)

    @field_validator("idempotency_key")
    @classmethod
    def clean_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Idempotency key must not be blank")
        return value


class ReservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    variant_id: UUID
    warehouse_id: UUID
    quantity: Decimal
    idempotency_key: str
    status: str
    expires_at: datetime
    created_at: datetime
    completed_at: datetime | None


class ReservationExpiryResponse(BaseModel):
    expired_count: int


class DigitalAssetCreateRequest(BaseModel):
    asset: SecretStr = Field(min_length=1, max_length=10000)
    idempotency_key: str = Field(min_length=1, max_length=128)

    @field_validator("idempotency_key")
    @classmethod
    def clean_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Idempotency key must not be blank")
        return value


class DigitalAssetResponse(BaseModel):
    id: UUID
    variant_id: UUID
    status: str


class CustomerCreateRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)

    @field_validator("full_name")
    @classmethod
    def clean_full_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name must not be blank")
        return value

    @field_validator("email")
    @classmethod
    def normalize_optional_email(cls, value: EmailStr | None) -> str | None:
        return str(value).strip().lower() if value is not None else None


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    full_name: str
    email: EmailStr | None
    phone: str | None
    created_at: datetime


class AddressCreateRequest(BaseModel):
    label: str = Field(default="", max_length=80)
    recipient_name: str = Field(min_length=1, max_length=160)
    phone: str = Field(min_length=1, max_length=32)
    address: dict[str, str] = Field(min_length=1)
    is_default: bool = False

    @field_validator("recipient_name", "phone")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value


class AddressResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    customer_id: UUID
    label: str
    recipient_name: str
    phone: str
    address: dict[str, str]
    is_default: bool
    created_at: datetime


class CartCreateRequest(BaseModel):
    customer_id: UUID


class CartItemCreateRequest(BaseModel):
    variant_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)


class CartItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    variant_id: UUID
    quantity: Decimal


class CartResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    status: str
    items: list[CartItemResponse]
    created_at: datetime
    updated_at: datetime


class CheckoutRequest(BaseModel):
    checkout_key: str = Field(min_length=1, max_length=128)
    warehouse_id: UUID | None = None
    shipping_address_id: UUID | None = None

    @field_validator("checkout_key")
    @classmethod
    def clean_checkout_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Checkout key must not be blank")
        return value


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    variant_id: UUID
    stock_reservation_id: UUID | None
    product_name_snapshot: str
    variant_name_snapshot: str
    sku_snapshot: str
    product_type: str
    quantity: Decimal
    unit_price_minor: int
    line_total_minor: int
    fulfillment_status: str


class OrderResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    checkout_key: str
    source: str
    currency: str
    subtotal_minor: int
    total_minor: int
    payment_status: str
    fulfillment_status: str
    shipping_address_snapshot: dict[str, str] | None
    items: list[OrderItemResponse]
    created_at: datetime


class DigitalDeliveryItem(BaseModel):
    order_item_id: UUID
    product_name: str
    sku: str
    asset: str


class DigitalDeliveryResponse(BaseModel):
    order_id: UUID
    items: list[DigitalDeliveryItem]


class OnboardingResponse(BaseModel):
    user: UserResponse
    tenant: TenantResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int