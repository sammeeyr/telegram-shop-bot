from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_api.core.config import Settings
from commerce_api.core.security import decrypt_digital_asset, encrypt_digital_asset
from commerce_api.db.models import (
    DigitalAsset,
    DigitalAssetStatus,
    FulfillmentStatus,
    Order,
    OrderItem,
    Product,
    ProductType,
    ProductVariant,
    PaymentStatus,
    utcnow,
)
from commerce_api.schemas import DigitalDeliveryItem
from commerce_api.services.errors import Conflict, IdempotencyConflict, PaymentRequired, ResourceNotFound


async def add_digital_asset(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    variant_id: UUID,
    plaintext: str,
    idempotency_key: str,
    settings: Settings,
) -> DigitalAsset:
    variant = await session.scalar(
        select(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(
            ProductVariant.tenant_id == tenant_id,
            ProductVariant.id == variant_id,
            Product.product_type == ProductType.DIGITAL,
        )
    )
    if variant is None:
        raise ResourceNotFound("Digital product variant not found")
    existing = await session.scalar(
        select(DigitalAsset).where(
            DigitalAsset.tenant_id == tenant_id,
            DigitalAsset.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.variant_id != variant_id or decrypt_digital_asset(existing.ciphertext, settings) != plaintext:
            raise IdempotencyConflict("Idempotency key was already used for a different digital asset")
        return existing
    asset = DigitalAsset(
        tenant_id=tenant_id,
        variant_id=variant_id,
        ciphertext=encrypt_digital_asset(plaintext, settings),
        idempotency_key=idempotency_key,
        status=DigitalAssetStatus.AVAILABLE,
    )
    session.add(asset)
    await session.flush()
    return asset


async def release_paid_digital_assets(
    session: AsyncSession, *, tenant_id: UUID, order_id: UUID, settings: Settings
) -> list[DigitalDeliveryItem]:
    order = await session.scalar(
        select(Order)
        .where(Order.tenant_id == tenant_id, Order.id == order_id)
        .with_for_update()
    )
    if order is None:
        raise ResourceNotFound("Order not found")
    if order.payment_status != PaymentStatus.PAID:
        raise PaymentRequired("Digital delivery is locked until payment is verified")

    lines = list(
        (
            await session.scalars(
                select(OrderItem)
                .where(
                    OrderItem.tenant_id == tenant_id,
                    OrderItem.order_id == order_id,
                    OrderItem.product_type == ProductType.DIGITAL,
                )
                .order_by(OrderItem.created_at, OrderItem.id)
                .with_for_update()
            )
        ).all()
    )
    deliveries: list[DigitalDeliveryItem] = []
    for line in lines:
        assets = list(
            (
                await session.scalars(
                    select(DigitalAsset)
                    .where(
                        DigitalAsset.tenant_id == tenant_id,
                        DigitalAsset.order_item_id == line.id,
                        DigitalAsset.status.in_([DigitalAssetStatus.RESERVED, DigitalAssetStatus.DELIVERED]),
                    )
                    .order_by(DigitalAsset.created_at, DigitalAsset.id)
                    .with_for_update()
                )
            ).all()
        )
        if len(assets) != int(line.quantity):
            raise Conflict("Reserved digital assets do not match the order quantity")
        for asset in assets:
            if asset.status == DigitalAssetStatus.RESERVED:
                asset.status = DigitalAssetStatus.DELIVERED
                asset.delivered_at = datetime.now(UTC)
            deliveries.append(
                DigitalDeliveryItem(
                    order_item_id=line.id,
                    product_name=line.product_name_snapshot,
                    sku=line.sku_snapshot,
                    asset=decrypt_digital_asset(asset.ciphertext, settings),
                )
            )
        line.fulfillment_status = FulfillmentStatus.FULFILLED

    await session.flush()
    all_lines = list(
        (
            await session.scalars(
                select(OrderItem).where(OrderItem.tenant_id == tenant_id, OrderItem.order_id == order_id)
            )
        ).all()
    )
    if all_lines and all(line.fulfillment_status == FulfillmentStatus.FULFILLED for line in all_lines):
        order.fulfillment_status = FulfillmentStatus.FULFILLED
        order.updated_at = utcnow()
    return deliveries
