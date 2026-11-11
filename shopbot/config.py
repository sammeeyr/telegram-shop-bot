"""Application settings loaded from environment variables (or a ``.env`` file)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from shopbot.money import format_money, parse_money

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_URL = f"sqlite+aiosqlite:///{(PROJECT_ROOT / 'data' / 'shop.db').as_posix()}"

CURRENCY_SYMBOLS = {
    "USD": "$", "EUR": "€", "GBP": "£", "RUB": "₽", "UAH": "₴", "INR": "₹",
    "TRY": "₺", "BRL": "R$", "PLN": "zł ", "ILS": "₪", "THB": "฿", "CNY": "¥",
}
# Fiat currencies Crypto Pay can invoice in.
CRYPTOPAY_FIATS = {
    "USD", "EUR", "RUB", "BYN", "UAH", "GBP", "CNY", "KZT", "UZS", "GEL", "TRY",
    "AMD", "THB", "INR", "BRL", "IDR", "AZN", "AED", "PLN", "ILS",
}
DEFAULT_ASSETS = ("USDT", "TON", "BTC", "ETH", "LTC", "TRX", "BNB", "USDC")


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int] = frozenset()
    database_url: str = DEFAULT_DATABASE_URL
    shop_name: str = "Digital Shop"
    support_contact: str = ""
    currency: str = "USD"

    cryptopay_token: str = ""
    cryptopay_testnet: bool = False
    cryptopay_assets: tuple[str, ...] = DEFAULT_ASSETS

    min_deposit: int = 100  # cents
    max_deposit: int = 1_000_000
    deposit_presets: tuple[int, ...] = (500, 1000, 2500, 5000, 10000)
    invoice_ttl_minutes: int = 60
    max_pending_deposits: int = 3
    payment_poll_interval: int = 15

    low_stock_threshold: int = 5
    max_qty_per_order: int = 50
    notify_admins: bool = True

    @property
    def currency_symbol(self) -> str:
        return CURRENCY_SYMBOLS.get(self.currency, f"{self.currency} ")

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids

    def money(self, cents: int) -> str:
        return format_money(cents, self.currency_symbol)


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _get_bool(name: str, default: bool) -> bool:
    raw = _get(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = _get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a whole number, got {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ConfigError(f"{name} must be <= {maximum}")
    return value


def _get_money(name: str, default: str) -> int:
    raw = _get(name) or default
    cents = parse_money(raw)
    if cents is None:
        raise ConfigError(f"{name} must be a positive amount, got {raw!r}")
    return cents


def _get_list(name: str, default: str = "") -> list[str]:
    raw = _get(name) or default
    return [part.strip() for part in raw.split(",") if part.strip()]


def load_settings(env_file: str | os.PathLike[str] | None = None) -> Settings:
    load_dotenv(env_file or PROJECT_ROOT / ".env")

    bot_token = _get("BOT_TOKEN")
    if not bot_token:
        raise ConfigError("BOT_TOKEN is missing. Copy .env.example to .env and fill it in.")

    admin_ids: set[int] = set()
    for part in _get_list("ADMIN_IDS"):
        if not part.isdigit():
            raise ConfigError(f"ADMIN_IDS must contain numeric Telegram user IDs, got {part!r}")
        admin_ids.add(int(part))

    currency = (_get("CURRENCY") or "USD").upper()
    if currency not in CRYPTOPAY_FIATS:
        raise ConfigError(f"CURRENCY {currency!r} is not supported by Crypto Pay. Use one of: {', '.join(sorted(CRYPTOPAY_FIATS))}")

    presets: list[int] = []
    for part in _get_list("DEPOSIT_PRESETS", "5,10,25,50,100"):
        cents = parse_money(part)
        if cents is None:
            raise ConfigError(f"DEPOSIT_PRESETS contains an invalid amount: {part!r}")
        presets.append(cents)

    min_deposit = _get_money("MIN_DEPOSIT", "1")
    max_deposit = _get_money("MAX_DEPOSIT", "10000")
    if min_deposit > max_deposit:
        raise ConfigError("MIN_DEPOSIT cannot be greater than MAX_DEPOSIT")

    assets = tuple(a.upper() for a in _get_list("CRYPTOPAY_ASSETS")) or DEFAULT_ASSETS

    return Settings(
        bot_token=bot_token,
        admin_ids=frozenset(admin_ids),
        database_url=_get("DATABASE_URL") or DEFAULT_DATABASE_URL,
        shop_name=_get("SHOP_NAME") or "Digital Shop",
        support_contact=_get("SUPPORT_CONTACT"),
        currency=currency,
        cryptopay_token=_get("CRYPTOPAY_TOKEN"),
        cryptopay_testnet=_get_bool("CRYPTOPAY_TESTNET", False),
        cryptopay_assets=assets,
        min_deposit=min_deposit,
        max_deposit=max_deposit,
        deposit_presets=tuple(p for p in presets if min_deposit <= p <= max_deposit),
        invoice_ttl_minutes=_get_int("INVOICE_TTL_MINUTES", 60, minimum=5, maximum=44_640),
        max_pending_deposits=_get_int("MAX_PENDING_DEPOSITS", 3, minimum=1, maximum=50),
        payment_poll_interval=_get_int("PAYMENT_POLL_INTERVAL", 15, minimum=5, maximum=3600),
        low_stock_threshold=_get_int("LOW_STOCK_THRESHOLD", 5, minimum=0),
        max_qty_per_order=_get_int("MAX_QTY_PER_ORDER", 50, minimum=1, maximum=1000),
        notify_admins=_get_bool("NOTIFY_ADMINS", True),
    )
