"""Payment provider interface. Implement this to add another gateway."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, Sequence


class InvoiceStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    EXPIRED = "expired"


@dataclass(frozen=True)
class ProviderInvoice:
    external_id: str
    status: InvoiceStatus
    pay_url: str | None = None
    paid_asset: str | None = None
    paid_amount: str | None = None


class PaymentProviderError(Exception):
    pass


class PaymentProvider(Protocol):
    name: str

    async def create_invoice(
        self, *, deposit_id: int, user_id: int, amount: int, description: str, expires_in: int
    ) -> ProviderInvoice: ...

    async def get_invoices(self, external_ids: Sequence[str]) -> dict[str, ProviderInvoice]: ...

    async def cancel_invoice(self, external_id: str) -> bool: ...

    async def close(self) -> None: ...
