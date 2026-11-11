"""Catalog browsing, checkout and purchasing."""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from shopbot.bot import keyboards as kb
from shopbot.bot import texts
from shopbot.bot.callbacks import BuyCb, CategoryCb, Nav, ProductCb, QtyCb
from shopbot.bot.delivery import deliver_order
from shopbot.bot.notify import notify_admins
from shopbot.bot.utils import show
from shopbot.config import Settings
from shopbot.db.models import User
from shopbot.services import catalog, inventory, orders
from shopbot.services.catalog import ProductView
from shopbot.services.errors import InsufficientBalance, ShopError

logger = logging.getLogger(__name__)
router = Router(name="shop")

# Guards against double-taps on "Confirm & pay" creating two orders.
_purchases_in_flight: set[int] = set()

UNAVAILABLE = "This product is no longer available."


def _max_quantity(view: ProductView, settings: Settings) -> int:
    if view.available is None:
        return 1  # same content for everyone: buying twice makes no sense
    return min(settings.max_qty_per_order, view.available)


@router.message(F.text == texts.BTN_SHOP)
async def shop_message(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    categories = await catalog.list_categories(session)
    await message.answer(texts.shop_categories(bool(categories)), reply_markup=kb.shop_categories(categories))


@router.callback_query(Nav.filter(F.to == "shop"))
async def shop_callback(call: CallbackQuery, session: AsyncSession) -> None:
    categories = await catalog.list_categories(session)
    await show(call, texts.shop_categories(bool(categories)), kb.shop_categories(categories))
    await call.answer()


@router.callback_query(CategoryCb.filter())
async def category_callback(call: CallbackQuery, callback_data: CategoryCb, session: AsyncSession, settings: Settings) -> None:
    category = await catalog.get_category(session, callback_data.id)
    if category is None or not category.is_active:
        await call.answer("This category is no longer available.", show_alert=True)
        return
    views = await catalog.list_products(session, category.id)
    await show(call, texts.shop_category(category, views), kb.shop_products(views, settings))
    await call.answer()


@router.callback_query(ProductCb.filter())
async def product_callback(
    call: CallbackQuery, callback_data: ProductCb, session: AsyncSession, user: User, settings: Settings
) -> None:
    view = await catalog.get_visible_product_view(session, callback_data.id)
    if view is None:
        await call.answer(UNAVAILABLE, show_alert=True)
        return
    await show(call, texts.product_card(view, user.balance, settings), kb.product_card(view))
    await call.answer()


@router.callback_query(QtyCb.filter())
async def checkout_callback(
    call: CallbackQuery, callback_data: QtyCb, session: AsyncSession, user: User, settings: Settings
) -> None:
    view = await catalog.get_visible_product_view(session, callback_data.id)
    if view is None:
        await call.answer(UNAVAILABLE, show_alert=True)
        return
    max_qty = _max_quantity(view, settings)
    if max_qty < 1:
        await call.answer("❌ Out of stock.", show_alert=True)
        await show(call, texts.product_card(view, user.balance, settings), kb.product_card(view))
        return
    qty = min(max(callback_data.qty, 1), max_qty)
    total = view.product.price * qty
    await show(
        call,
        texts.checkout(view.product, qty, total, user.balance, settings),
        kb.checkout(view.product, qty, max_qty, total, user.balance >= total, settings),
    )
    await call.answer()


@router.callback_query(BuyCb.filter())
async def buy_callback(
    call: CallbackQuery, callback_data: BuyCb, session: AsyncSession, user: User, settings: Settings, bot: Bot
) -> None:
    if user.id in _purchases_in_flight:
        await call.answer("⏳ Processing your order…")
        return
    _purchases_in_flight.add(user.id)
    try:
        try:
            result = await orders.purchase(
                session,
                user_id=user.id,
                product_id=callback_data.id,
                quantity=callback_data.qty,
                max_quantity=settings.max_qty_per_order,
                expected_unit_price=callback_data.price,
            )
        except InsufficientBalance as exc:
            await call.answer(
                f"💸 Not enough balance: you need {settings.money(exc.required)}, "
                f"you have {settings.money(exc.balance)}. Top up first.",
                show_alert=True,
            )
            return
        except ShopError as exc:
            await call.answer(f"⚠️ {exc}", show_alert=True)
            return

        order = result.order
        await call.answer("✅ Purchase successful!")
        await show(call, texts.purchase_success(order, result.new_balance, settings), kb.after_purchase())
        try:
            await deliver_order(bot, user.id, order)
        except TelegramAPIError:
            logger.exception("Delivery of order #%s failed", order.id)
            await bot.send_message(
                user.id, f"⚠️ Couldn't send your items right now. Open 📦 My Orders → #{order.id} to get them."
            )
        logger.info("Order #%s: user %s bought %s x%s", order.id, user.id, order.product_name, order.quantity)

        if settings.notify_admins:
            await notify_admins(bot, settings, texts.admin_new_order(order, user, settings))
        remaining = await inventory.low_stock_check(session, order.product_id, settings.low_stock_threshold)
        if remaining is not None:
            await notify_admins(bot, settings, texts.admin_low_stock(order.product_name, remaining))
    finally:
        _purchases_in_flight.discard(user.id)
