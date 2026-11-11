from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_api.db.models import Order, PaymentAttempt, PaymentStatus, utcnow
from commerce_api.services.errors import Conflict, ResourceNotFound


@dataclass(frozen=True)
class VerifiedPayment:
    """Evidence produced only after a provider adapter verifies settlement."""

    tenant_id: UUID
    order_id: UUID
    provider: str
    provider_reference: str
    amount_minor: int
    currency: str
    verified_at: datetime


async def record_verified_payment(session: AsyncSession, evidence: VerifiedPayment) -> Order:
    if not evidence.provider.strip() or not evidence.provider_reference.strip():
        raise Conflict("Verified payment requires a provider and reference")
    if evidence.verified_at.tzinfo is None:
        raise Conflict("Verified payment timestamp must include a timezone")

    order = await session.scalar(
        select(Order)
        .where(Order.tenant_id == evidence.tenant_id, Order.id == evidence.order_id)
        .with_for_update()
    )
    if order is None:
        raise ResourceNotFound("Order not found")
    if evidence.amount_minor != order.total_minor or evidence.currency != order.currency:
        raise Conflict("Verified payment amount or currency does not match the order")

    attempt = await session.scalar(
        select(PaymentAttempt)
        .where(PaymentAttempt.tenant_id == evidence.tenant_id, PaymentAttempt.order_id == evidence.order_id)
        .with_for_update()
    )
    if attempt is None:
        raise Conflict("Payment attempt not found")
    if order.payment_status == PaymentStatus.PAID:
        if attempt.provider == evidence.provider and attempt.provider_reference == evidence.provider_reference:
            return order
        raise Conflict("Order already has a different settled payment")
    if attempt.status != PaymentStatus.PENDING:
        raise Conflict("Payment attempt is not pending")

    attempt.provider = evidence.provider
    attempt.provider_reference = evidence.provider_reference
    attempt.status = PaymentStatus.PAID
    attempt.verified_at = evidence.verified_at
    order.payment_status = PaymentStatus.PAID
    order.updated_at = utcnow()
    await session.flush()
    return order
