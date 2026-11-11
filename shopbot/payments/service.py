"""Orchestrates deposits between the database and a payment provider."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shopbot.db.models import Deposit, DepositStatus, utcnow
from shopbot.payments.base import InvoiceStatus, PaymentProvider, PaymentProviderError, ProviderInvoice
from shopbot.services import deposits
from shopbot.services.deposits import CreditResult
from shopbot.services.errors import NotFound

logger = logging.getLogger(__name__)

# An invoice the provider no longer returns is given up on after this long past its TTL.
MISSING_INVOICE_GRACE = timedelta(days=1)
# A deposit row whose invoice creation never finished.
STUCK_DEPOSIT_AGE = timedelta(minutes=10)


@dataclass
class CheckResult:
    deposit: Deposit
    credited: CreditResult | None = None  # set only if *this* call credited the balance


class PaymentService:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        provider: PaymentProvider,
        *,
        invoice_ttl_minutes: int,
        shop_name: str,
    ) -> None:
        self._sessionmaker = sessionmaker
        self.provider = provider
        self._ttl = timedelta(minutes=invoice_ttl_minutes)
        self._shop_name = shop_name

    async def create_deposit_invoice(self, user_id: int, amount: int) -> Deposit:
        async with self._sessionmaker() as session:
            deposit = await deposits.create_deposit(session, user_id=user_id, amount=amount, provider=self.provider.name)
        try:
            invoice = await self.provider.create_invoice(
                deposit_id=deposit.id,
                user_id=user_id,
                amount=amount,
                description=f"{self._shop_name}: balance top-up #{deposit.id}",
                expires_in=int(self._ttl.total_seconds()),
            )
        except PaymentProviderError:
            async with self._sessionmaker() as session:
                await deposits.set_status_if_pending(session, deposit.id, DepositStatus.FAILED)
            raise
        async with self._sessionmaker() as session:
            return await deposits.attach_invoice(
                session, deposit.id, external_id=invoice.external_id, pay_url=invoice.pay_url,
                expires_at=utcnow() + self._ttl,
            )

    async def check(self, deposit_id: int) -> CheckResult:
        """Check a single deposit right now (the "I've paid" button)."""
        async with self._sessionmaker() as session:
            deposit = await deposits.get_deposit(session, deposit_id)
        if deposit is None:
            raise NotFound("Invoice not found.")
        if deposit.status != DepositStatus.PENDING or not deposit.external_id:
            return CheckResult(deposit)
        invoices = await self.provider.get_invoices([deposit.external_id])
        return await self._apply(deposit, invoices.get(deposit.external_id))

    async def sync_pending(self) -> list[CreditResult]:
        """Poll the provider for every pending deposit. Returns newly credited deposits."""
        async with self._sessionmaker() as session:
            pending = await deposits.list_pending(session, provider=self.provider.name)
        if not pending:
            return []

        now = utcnow()
        with_invoice = [d for d in pending if d.external_id]
        for stuck in (d for d in pending if not d.external_id and now - d.created_at > STUCK_DEPOSIT_AGE):
            async with self._sessionmaker() as session:
                await deposits.set_status_if_pending(session, stuck.id, DepositStatus.FAILED)

        invoices: dict[str, ProviderInvoice] = {}
        ids = [d.external_id for d in with_invoice if d.external_id]
        for start in range(0, len(ids), 100):
            invoices.update(await self.provider.get_invoices(ids[start : start + 100]))

        credited: list[CreditResult] = []
        for deposit in with_invoice:
            try:
                result = await self._apply(deposit, invoices.get(deposit.external_id or ""))
            except Exception:
                logger.exception("Failed to apply status for deposit #%s", deposit.id)
                continue
            if result.credited:
                credited.append(result.credited)
        return credited

    async def cancel(self, deposit_id: int, user_id: int) -> bool:
        async with self._sessionmaker() as session:
            deposit = await deposits.get_deposit(session, deposit_id)
            if deposit is None or deposit.user_id != user_id or deposit.status != DepositStatus.PENDING:
                return False
            if deposit.external_id and not await self.provider.cancel_invoice(deposit.external_id):
                return False  # may have just been paid; the poller will settle it
            return await deposits.set_status_if_pending(session, deposit_id, DepositStatus.CANCELLED)

    async def close(self) -> None:
        await self.provider.close()

    async def _apply(self, deposit: Deposit, invoice: ProviderInvoice | None) -> CheckResult:
        async with self._sessionmaker() as session:
            if invoice is None:
                expires_at = deposit.expires_at or deposit.created_at + self._ttl
                if utcnow() > expires_at + MISSING_INVOICE_GRACE:
                    await deposits.set_status_if_pending(session, deposit.id, DepositStatus.EXPIRED)
            elif invoice.status == InvoiceStatus.PAID:
                credited = await deposits.credit_deposit(
                    session, deposit.id, paid_asset=invoice.paid_asset, paid_amount=invoice.paid_amount
                )
                if credited is not None:
                    logger.info(
                        "Deposit #%s credited: user %s +%s", deposit.id, deposit.user_id, deposit.amount
                    )
                    return CheckResult(credited.deposit, credited)
            elif invoice.status == InvoiceStatus.EXPIRED:
                await deposits.set_status_if_pending(session, deposit.id, DepositStatus.EXPIRED)
            fresh = await deposits.get_deposit(session, deposit.id)
            return CheckResult(fresh or deposit)


__all__ = ["CheckResult", "PaymentService", "PaymentProviderError"]
