from __future__ import annotations

from typing import Sequence

from shopbot.db.models import DepositStatus, User
from shopbot.payments import InvoiceStatus, PaymentService, ProviderInvoice
from shopbot.payments.cryptopay import CryptoPayProvider


class FakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self.invoices: dict[str, ProviderInvoice] = {}
        self.cancelled: list[str] = []

    async def create_invoice(self, *, deposit_id, user_id, amount, description, expires_in) -> ProviderInvoice:
        invoice = ProviderInvoice(str(1000 + deposit_id), InvoiceStatus.PENDING, f"https://pay/{deposit_id}")
        self.invoices[invoice.external_id] = invoice
        return invoice

    async def get_invoices(self, external_ids: Sequence[str]) -> dict[str, ProviderInvoice]:
        return {i: self.invoices[i] for i in external_ids if i in self.invoices}

    async def cancel_invoice(self, external_id: str) -> bool:
        self.cancelled.append(external_id)
        return True

    async def close(self) -> None:
        pass

    def set_status(self, external_id: str, status: InvoiceStatus) -> None:
        self.invoices[external_id] = ProviderInvoice(external_id, status, None, "USDT", "10.01")


async def test_poller_credits_paid_and_expires_expired(sessionmaker, make_user):
    await make_user(1)
    provider = FakeProvider()
    service = PaymentService(sessionmaker, provider, invoice_ttl_minutes=60, shop_name="Test")

    paid = await service.create_deposit_invoice(1, 1000)
    expired = await service.create_deposit_invoice(1, 500)
    assert paid.pay_url and paid.external_id

    provider.set_status(paid.external_id, InvoiceStatus.PAID)
    provider.set_status(expired.external_id, InvoiceStatus.EXPIRED)

    credited = await service.sync_pending()
    assert [c.deposit.id for c in credited] == [paid.id]
    assert credited[0].new_balance == 1000
    assert await service.sync_pending() == []  # nothing credited twice

    check = await service.check(expired.id)
    assert check.deposit.status == DepositStatus.EXPIRED and check.credited is None
    async with sessionmaker() as session:
        assert (await session.get(User, 1)).balance == 1000


async def test_manual_check_and_cancel(sessionmaker, make_user):
    await make_user(1)
    await make_user(2)
    provider = FakeProvider()
    service = PaymentService(sessionmaker, provider, invoice_ttl_minutes=60, shop_name="Test")

    deposit = await service.create_deposit_invoice(1, 700)
    assert (await service.check(deposit.id)).deposit.status == DepositStatus.PENDING
    assert not await service.cancel(deposit.id, user_id=2)  # not the owner
    assert await service.cancel(deposit.id, user_id=1)
    assert provider.cancelled == [deposit.external_id]

    other = await service.create_deposit_invoice(1, 300)
    provider.set_status(other.external_id, InvoiceStatus.PAID)
    result = await service.check(other.id)
    assert result.credited is not None and result.credited.new_balance == 300


def test_cryptopay_invoice_mapping():
    invoice = CryptoPayProvider._to_invoice(
        {"invoice_id": 42, "status": "paid", "bot_invoice_url": "https://t.me/CryptoBot?start=IV42",
         "paid_asset": "USDT", "paid_amount": "10.02"}
    )
    assert invoice == ProviderInvoice("42", InvoiceStatus.PAID, "https://t.me/CryptoBot?start=IV42", "USDT", "10.02")
    legacy = CryptoPayProvider._to_invoice({"invoice_id": 7, "status": "active", "pay_url": "https://x"})
    assert legacy.status == InvoiceStatus.PENDING and legacy.pay_url == "https://x"
