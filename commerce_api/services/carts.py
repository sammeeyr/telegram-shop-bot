from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_api.db.models import Cart, CartItem, CartStatus, Customer, Product, ProductVariant
from commerce_api.services.errors import Conflict, InvalidQuantity, ResourceNotFound


async def create_cart(session: AsyncSession, *, tenant_id: UUID, customer_id: UUID) -> Cart:
    if await session.scalar(
        select(Customer.id).where(Customer.tenant_id == tenant_id, Customer.id == customer_id)
    ) is None:
        raise ResourceNotFound("Customer not found")
    cart = Cart(tenant_id=tenant_id, customer_id=customer_id, status=CartStatus.ACTIVE)
    session.add(cart)
    await session.flush()
    return cart


async def get_cart(session: AsyncSession, *, tenant_id: UUID, cart_id: UUID) -> Cart:
    cart = await session.scalar(
        select(Cart).where(Cart.tenant_id == tenant_id, Cart.id == cart_id)
    )
    if cart is None:
        raise ResourceNotFound("Cart not found")
    return cart


async def list_cart_items(
    session: AsyncSession, *, tenant_id: UUID, cart_id: UUID
) -> list[CartItem]:
    await get_cart(session, tenant_id=tenant_id, cart_id=cart_id)
    rows = await session.scalars(
        select(CartItem)
        .where(CartItem.tenant_id == tenant_id, CartItem.cart_id == cart_id)
        .order_by(CartItem.created_at, CartItem.id)
    )
    return list(rows.all())


async def add_item(
    session: AsyncSession, *, tenant_id: UUID, cart_id: UUID, variant_id: UUID, quantity: Decimal
) -> CartItem:
    if not quantity.is_finite() or quantity <= 0 or max(0, -quantity.as_tuple().exponent) > 3:
        raise InvalidQuantity("Cart quantity must be positive with at most three decimal places")
    cart = await get_cart(session, tenant_id=tenant_id, cart_id=cart_id)
    if cart.status != CartStatus.ACTIVE:
        raise Conflict("Only active carts can be changed")
    variant = await session.scalar(
        select(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(
            ProductVariant.tenant_id == tenant_id,
            ProductVariant.id == variant_id,
            ProductVariant.is_active.is_(True),
            Product.is_active.is_(True),
        )
    )
    if variant is None:
        raise ResourceNotFound("Active product variant not found")
    item = await session.scalar(
        select(CartItem).where(
            CartItem.tenant_id == tenant_id,
            CartItem.cart_id == cart_id,
            CartItem.variant_id == variant_id,
        )
    )
    if item is None:
        item = CartItem(tenant_id=tenant_id, cart_id=cart_id, variant_id=variant_id, quantity=quantity)
        session.add(item)
    else:
        item.quantity += quantity
    await session.flush()
    return item