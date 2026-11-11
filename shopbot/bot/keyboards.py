"""User-facing keyboards."""
from __future__ import annotations

from typing import Callable

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from shopbot.bot import texts
from shopbot.bot.callbacks import (
    BuyCb, CategoryCb, DepositCb, DepositsPage, Nav, OrderCb, OrdersPage, ProductCb, QtyCb, TopUpCb,
)
from shopbot.bot.utils import fmt_date, truncate
from shopbot.config import Settings
from shopbot.db.models import Category, Deposit, DepositStatus, Order, Product
from shopbot.services.catalog import ProductView


def btn(text: str, data: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data.pack())


def url_btn(text: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=url)


def markup(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[row for row in rows if row])


def pager_row(page: int, pages: int, make: Callable[[int], CallbackData]) -> list[InlineKeyboardButton]:
    if pages <= 1:
        return []
    row = []
    if page > 0:
        row.append(btn("◀️", make(page - 1)))
    row.append(btn(f"{page + 1}/{pages}", Nav(to="noop")))
    if page < pages - 1:
        row.append(btn("▶️", make(page + 1)))
    return row


def main_menu(is_admin: bool) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=texts.BTN_SHOP), KeyboardButton(text=texts.BTN_PROFILE)],
        [KeyboardButton(text=texts.BTN_TOPUP), KeyboardButton(text=texts.BTN_ORDERS)],
        [KeyboardButton(text=texts.BTN_SUPPORT)],
    ]
    if is_admin:
        rows[2].append(KeyboardButton(text=texts.BTN_ADMIN))
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, input_field_placeholder="Choose an option…")


def profile() -> InlineKeyboardMarkup:
    return markup(
        [btn("💰 Top up", Nav(to="topup"))],
        [btn("📦 My orders", OrdersPage(page=0)), btn("🧾 Top-up history", DepositsPage(page=0))],
    )


# ── Shop ─────────────────────────────────────────────────────────────────


def shop_categories(categories: list[tuple[Category, int]]) -> InlineKeyboardMarkup:
    return markup(*([btn(f"📂 {truncate(c.name, 40)} ({n})", CategoryCb(id=c.id))] for c, n in categories))


def shop_products(views: list[ProductView], settings: Settings) -> InlineKeyboardMarkup:
    rows = []
    for view in views:
        if view.available is None:
            stock = "♾"
        elif view.available > 0:
            stock = f"{view.available} pcs"
        else:
            stock = "sold out"
        label = f"{truncate(view.product.name, 32)} · {settings.money(view.product.price)} · {stock}"
        rows.append([btn(label, ProductCb(id=view.product.id))])
    rows.append([btn("⬅️ Categories", Nav(to="shop"))])
    return markup(*rows)


def product_card(view: ProductView) -> InlineKeyboardMarkup:
    product = view.product
    buy_row = [btn("🛒 Buy", QtyCb(id=product.id, qty=1))] if view.in_stock else []
    return markup(buy_row, [btn("⬅️ Back", CategoryCb(id=product.category_id))])


def checkout(product: Product, qty: int, max_qty: int, total: int, affordable: bool, settings: Settings) -> InlineKeyboardMarkup:
    adjust = []
    for delta in (-10, -1, 0, 1, 10):
        if delta == 0:
            adjust.append(btn(f"× {qty}", Nav(to="noop")))
            continue
        new_qty = min(max(qty + delta, 1), max_qty)
        if new_qty != qty and (abs(delta) == 1 or max_qty > 10):
            adjust.append(btn(f"{delta:+d}", QtyCb(id=product.id, qty=new_qty)))
    if max_qty <= 1:
        adjust = []

    if affordable:
        action = [btn(f"✅ Confirm & pay {settings.money(total)}", BuyCb(id=product.id, qty=qty, price=product.price))]
    else:
        action = [btn("💰 Top up balance", Nav(to="topup"))]
    return markup(adjust, action, [btn("⬅️ Back", ProductCb(id=product.id))])


def after_purchase() -> InlineKeyboardMarkup:
    return markup([btn("🛍 Continue shopping", Nav(to="shop")), btn("📦 My orders", OrdersPage(page=0))])


# ── Orders ───────────────────────────────────────────────────────────────


def orders_list(orders: list[Order], page: int, pages: int, settings: Settings) -> InlineKeyboardMarkup:
    rows = [
        [btn(
            f"#{o.id} · {truncate(o.product_name, 24)} ×{o.quantity} · {settings.money(o.total)} · {fmt_date(o.created_at)}",
            OrderCb(id=o.id, action="view", page=page),
        )]
        for o in orders
    ]
    rows.append(pager_row(page, pages, lambda p: OrdersPage(page=p)))
    return markup(*rows)


def order_detail(order: Order, page: int) -> InlineKeyboardMarkup:
    return markup(
        [btn("📥 Show my items", OrderCb(id=order.id, action="items", page=page))],
        [btn("⬅️ Back to orders", OrdersPage(page=page))],
    )


# ── Top-ups ──────────────────────────────────────────────────────────────


def topup_menu(settings: Settings, available: bool) -> InlineKeyboardMarkup:
    if not available:
        return markup([btn("🧾 Top-up history", DepositsPage(page=0))])
    presets = [btn(settings.money(amount), TopUpCb(amount=amount)) for amount in settings.deposit_presets]
    rows = [presets[i : i + 3] for i in range(0, len(presets), 3)]
    rows.append([btn("✏️ Custom amount", TopUpCb(amount=0))])
    rows.append([btn("🧾 Top-up history", DepositsPage(page=0))])
    return markup(*rows)


def invoice(deposit: Deposit, settings: Settings) -> InlineKeyboardMarkup:
    rows = []
    if deposit.pay_url:
        rows.append([url_btn(f"💳 Pay {settings.money(deposit.amount)}", deposit.pay_url)])
    rows.append([btn("🔄 I've paid, check", DepositCb(id=deposit.id, action="check"))])
    rows.append([btn("❌ Cancel invoice", DepositCb(id=deposit.id, action="cancel"))])
    return markup(*rows)


def deposit_done() -> InlineKeyboardMarkup:
    return markup([btn("🛍 Go shopping", Nav(to="shop")), btn("👤 Profile", Nav(to="profile"))])


def deposits_list(deposits: list[Deposit], page: int, pages: int, settings: Settings) -> InlineKeyboardMarkup:
    rows = [
        [btn(f"⏳ Open invoice #{d.id} · {settings.money(d.amount)}", DepositCb(id=d.id, action="view"))]
        for d in deposits
        if d.status == DepositStatus.PENDING
    ]
    rows.append(pager_row(page, pages, lambda p: DepositsPage(page=p)))
    rows.append([btn("💰 New top-up", Nav(to="topup"))])
    return markup(*rows)
