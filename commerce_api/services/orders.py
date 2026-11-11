from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_api.db.models import (
    Cart,
    CartItem,
    CartStatus,
    CustomerAddress,
    DigitalAsset,
    DigitalAssetStatus,
    FulfillmentStatus,
    Order,
    OrderItem,
    PaymentAttempt,
    PaymentStatus,
    Product,
    ProductType,
    ProductVariant,
    StockReservation,
    Warehouse,
    utcnow,
)
from commerce_api.schemas import CheckoutRequest
from commerce_api.services import inventory
from commerce_api.services.errors import Conflict, InsufficientStock, InvalidQuantity, ResourceNotFound


def _minor_total(unit_price_minor: int, quantity: Decimal) -> int:
    total = Decimal(unit_price_minor) * quantity
    integral = total.to_integral_value()
    if total != integral:
        raise InvalidQuantity("Line total must resolve to whole minor currency units")
    return int(integral)


async def checkout_cart(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    cart_id: UUID,
    actor_user_id: UUID,
    values: CheckoutRequest,
) -> Order:
    existing_order = await session.scalar(
        select(Order).where(Order.tenant_id == tenant_id, Order.checkout_key == values.checkout_key)
    )
    if existing_order is not None:
        if existing_order.customer_id != (
            await session.scalar(
                select(Cart.customer_id).where(Cart.tenant_id == tenant_id, Cart.id == cart_id)
            )
        ):
            raise Conflict("Checkout key is already associated with another order")
        return existing_order

    cart = await session.scalar(
        select(Cart)
        .where(Cart.tenant_id == tenant_id, Cart.id == cart_id)
        .with_for_update()
    )
    if cart is None:
        raise ResourceNotFound("Cart not found")
    if cart.status != CartStatus.ACTIVE:
        if cart.checkout_key == values.checkout_key:
            existing_order = await session.scalar(
                select(Order).where(Order.tenant_id == tenant_id, Order.checkout_key == values.checkout_key)
            )
            if existing_order is not None:
                return existing_order
        raise Conflict("Only active carts can be checked out")

    rows = await session.execute(
        select(CartItem, ProductVariant, Product)
        .join(ProductVariant, (ProductVariant.id == CartItem.variant_id) & (ProductVariant.tenant_id == tenant_id))
        .join(Product, (Product.id == ProductVariant.product_id) & (Product.tenant_id == tenant_id))
        .where(CartItem.tenant_id == tenant_id, CartItem.cart_id == cart_id)
        .order_by(CartItem.created_at, CartItem.id)
    )
    lines = list(rows.all())
    if not lines:
        raise Conflict("Cannot check out an empty cart")

    currencies = {product.currency for _, _, product in lines}
    if len(currencies) != 1:
        raise Conflict("All cart items must use the same currency")
    has_physical = any(product.product_type == ProductType.PHYSICAL for _, _, product in lines)
    if has_physical and values.warehouse_id is None:
        raise InvalidQuantity("A warehouse is required for physical products")

    address_snapshot = None
    if values.shipping_address_id is not None:
        address = await session.scalar(
            select(CustomerAddress).where(
                CustomerAddress.tenant_id == tenant_id,
                CustomerAddress.customer_id == cart.customer_id,
                CustomerAddress.id == values.shipping_address_id,
            )
        )
        if address is None:
            raise ResourceNotFound("Shipping address not found")
        address_snapshot = {
            "label": address.label,
            "recipient_name": address.recipient_name,
            "phone": address.phone,
            **address.address,
        }
    elif has_physical:
        raise InvalidQuantity("A shipping address is required for physical products")

    for _, variant, product in lines:
        if not product.is_active or not variant.is_active:
            raise Conflict("Cart contains an inactive product")

    order_id = uuid4()
    subtotal_minor = 0
    line_values: list[tuple[CartItem, ProductVariant, Product, int, int]] = []
    for cart_item, variant, product in lines:
        unit_price_minor = variant.price_minor if variant.price_minor is not None else product.unit_price_minor
        line_total_minor = _minor_total(unit_price_minor, cart_item.quantity)
        subtotal_minor += line_total_minor
        line_values.append((cart_item, variant, product, unit_price_minor, line_total_minor))

    order = Order(
        id=order_id,
        tenant_id=tenant_id,
        customer_id=cart.customer_id,
        shipping_address_id=values.shipping_address_id,
        shipping_address_snapshot=address_snapshot,
        checkout_key=values.checkout_key,
        source="api",
        currency=currencies.pop(),
        subtotal_minor=subtotal_minor,
        total_minor=subtotal_minor,
        payment_status=PaymentStatus.PENDING,
        fulfillment_status=FulfillmentStatus.RESERVED,
    )
    session.add(order)
    await session.flush()

    for cart_item, variant, product, unit_price_minor, line_total_minor in line_values:
        if product.product_type == ProductType.DIGITAL:
            if cart_item.quantity != cart_item.quantity.to_integral_value():
                raise InvalidQuantity("Digital products must be purchased in whole units")
            stock_reservation_id = None
        else:
            reservation = await inventory.reserve_stock(
                session,
                tenant_id=tenant_id,
                variant_id=variant.id,
                warehouse_id=values.warehouse_id,
                quantity=cart_item.quantity,
                idempotency_key=f"order:{order_id}:variant:{variant.id}",
                actor_user_id=actor_user_id,
            )
            stock_reservation_id = reservation.id

        order_item = OrderItem(
            tenant_id=tenant_id,
            order_id=order_id,
            variant_id=variant.id,
            stock_reservation_id=stock_reservation_id,
            product_name_snapshot=product.name,
            variant_name_snapshot=variant.name,
            sku_snapshot=variant.sku,
            product_type=product.product_type,
            quantity=cart_item.quantity,
            unit_price_minor=unit_price_minor,
            line_total_minor=line_total_minor,
            fulfillment_status=FulfillmentStatus.RESERVED,
        )
        session.add(order_item)
        await session.flush()

        if product.product_type == ProductType.DIGITAL:
            requested_assets = int(cart_item.quantity)
            assets = list(
                (
                    await session.scalars(
                        select(DigitalAsset)
                        .where(
                            DigitalAsset.tenant_id == tenant_id,
                            DigitalAsset.variant_id == variant.id,
                            DigitalAsset.status == DigitalAssetStatus.AVAILABLE,
                        )
                        .order_by(DigitalAsset.created_at, DigitalAsset.id)
                        .limit(requested_assets)
                        .with_for_update(skip_locked=True)
                    )
                ).all()
            )
            if len(assets) != requested_assets:
                raise InsufficientStock("Insufficient digital assets available")
            for asset in assets:
                asset.status = DigitalAssetStatus.RESERVED
                asset.order_item_id = order_item.id

    cart.status = CartStatus.CHECKED_OUT
    cart.checkout_key = values.checkout_key
    cart.updated_at = utcnow()
    session.add(
        PaymentAttempt(
            tenant_id=tenant_id,
            order_id=order_id,
            provider="unconfigured",
            provider_reference=None,
            idempotency_key=values.checkout_key,
            amount_minor=subtotal_minor,
            currency=order.currency,
            status=PaymentStatus.PENDING,
        )
    )
    await session.flush()
    return order


async def get_order(
    session: AsyncSession, *, tenant_id: UUID, order_id: UUID
) -> tuple[Order, list[OrderItem]]:
    order = await session.scalar(
        select(Order).where(Order.tenant_id == tenant_id, Order.id == order_id)
    )
    if order is None:
        raise ResourceNotFound("Order not found")
    items = list(
        (
            await session.scalars(
                select(OrderItem)
                .where(OrderItem.tenant_id == tenant_id, OrderItem.order_id == order_id)
                .order_by(OrderItem.created_at, OrderItem.id)
            )
        ).all()
    )
    return order, items


async def list_customer_orders(
    session: AsyncSession, *, tenant_id: UUID, customer_id: UUID, offset: int, limit: int
) -> list[Order]:
    rows = await session.scalars(
        select(Order)
        .where(Order.tenant_id == tenant_id, Order.customer_id == customer_id)
        .order_by(Order.created_at.desc(), Order.id)
        .offset(offset)
        .limit(limit)
    )
    return list(rows.all())
