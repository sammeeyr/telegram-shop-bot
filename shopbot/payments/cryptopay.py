"""Crypto Pay API (@CryptoBot) client and payment provider.

Docs: https://help.crypt.bot/crypto-pay-api
Invoices are created in fiat (e.g. USD) and can be paid with any accepted
crypto asset; the payment status is polled, so no public webhook is required.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Sequence

import aiohttp

from shopbot.money import cents_to_decimal_str
from shopbot.payments.base import InvoiceStatus, PaymentProviderError, ProviderInvoice

logger = logging.getLogger(__name__)

_STATUS_MAP = {"active": InvoiceStatus.PENDING, "paid": InvoiceStatus.PAID, "expired": InvoiceStatus.EXPIRED}


class CryptoPayError(PaymentProviderError):
    def __init__(self, message: str, *, code: int | None = None, name: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.name = name


class CryptoPayClient:
    MAINNET_URL = "https://pay.crypt.bot/api/"
    TESTNET_URL = "https://testnet-pay.crypt.bot/api/"

    def __init__(self, token: str, *, testnet: bool = False, timeout: float = 20.0) -> None:
        self._token = token
        self._base_url = self.TESTNET_URL if testnet else self.MAINNET_URL
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self._timeout, headers={"Crypto-Pay-API-Token": self._token}
            )
        return self._session

    async def call(self, method: str, **params: Any) -> Any:
        payload = {key: value for key, value in params.items() if value is not None}
        session = await self._get_session()
        try:
            async with session.post(self._base_url + method, json=payload) as response:
                data = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            raise CryptoPayError(f"Crypto Pay {method} request failed: {exc!r}") from exc

        if not isinstance(data, dict) or not data.get("ok"):
            error = data.get("error") if isinstance(data, dict) else None
            code = error.get("code") if isinstance(error, dict) else None
            name = error.get("name") if isinstance(error, dict) else str(error)
            raise CryptoPayError(f"Crypto Pay {method} error: {name} ({code})", code=code, name=name)
        return data["result"]

    async def get_me(self) -> dict:
        return await self.call("getMe")

    async def create_invoice(self, **params: Any) -> dict:
        return await self.call("createInvoice", **params)

    async def get_invoices(self, invoice_ids: Sequence[int]) -> list[dict]:
        result = await self.call(
            "getInvoices", invoice_ids=",".join(str(i) for i in invoice_ids), count=min(max(len(invoice_ids), 1), 1000)
        )
        return list(result.get("items", [])) if isinstance(result, dict) else list(result or [])

    async def delete_invoice(self, invoice_id: int) -> bool:
        return bool(await self.call("deleteInvoice", invoice_id=invoice_id))

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()


class CryptoPayProvider:
    name = "cryptopay"

    def __init__(
        self,
        client: CryptoPayClient,
        *,
        fiat: str,
        accepted_assets: Sequence[str],
        bot_username: str | None = None,
    ) -> None:
        self.client = client
        self._fiat = fiat
        self._assets = list(accepted_assets)
        self._bot_username = bot_username

    async def create_invoice(
        self, *, deposit_id: int, user_id: int, amount: int, description: str, expires_in: int
    ) -> ProviderInvoice:
        params: dict[str, Any] = {
            "currency_type": "fiat",
            "fiat": self._fiat,
            "amount": cents_to_decimal_str(amount),
            "accepted_assets": ",".join(self._assets) if self._assets else None,
            "description": description[:1024],
            "payload": f"deposit:{deposit_id}:user:{user_id}",
            "expires_in": expires_in,
            "allow_comments": False,
        }
        if self._bot_username:
            params["paid_btn_name"] = "openBot"
            params["paid_btn_url"] = f"https://t.me/{self._bot_username}"
        return self._to_invoice(await self.client.create_invoice(**params))

    async def get_invoices(self, external_ids: Sequence[str]) -> dict[str, ProviderInvoice]:
        if not external_ids:
            return {}
        items = await self.client.get_invoices([int(i) for i in external_ids])
        invoices = (self._to_invoice(item) for item in items)
        return {invoice.external_id: invoice for invoice in invoices}

    async def cancel_invoice(self, external_id: str) -> bool:
        try:
            return await self.client.delete_invoice(int(external_id))
        except CryptoPayError as exc:
            logger.warning("Could not delete Crypto Pay invoice %s: %s", external_id, exc)
            return False

    async def close(self) -> None:
        await self.client.close()

    @staticmethod
    def _to_invoice(data: dict) -> ProviderInvoice:
        paid_asset = data.get("paid_asset")
        paid_amount = data.get("paid_amount")
        return ProviderInvoice(
            external_id=str(data["invoice_id"]),
            status=_STATUS_MAP.get(str(data.get("status")), InvoiceStatus.PENDING),
            pay_url=data.get("bot_invoice_url") or data.get("pay_url") or data.get("mini_app_invoice_url"),
            paid_asset=str(paid_asset) if paid_asset else None,
            paid_amount=str(paid_amount) if paid_amount else None,
        )
