"""Order history and re-delivery."""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from shopbot.bot import keyboards as kb
from shopbot.bot import texts
from shopbot.bot.callbacks import OrderCb, OrdersPage
from shopbot.bot.delivery import deliver_order
from shopbot.bot.utils import clamp_page, page_count, show
from shopbot.config import Settings
from shopbot.db.models import User
from shopbot.services import orders

router = Router(name="orders")
PER_PAGE = 8


async def _orders_screen(session: AsyncSession, user_id: int, page: int, settings: Settings):
    total = await orders.count_user_orders(session, user_id)
    pages = page_count(total, PER_PAGE)
    page = clamp_page(page, pages)
    items = await orders.list_user_orders(session, user_id, offset=page * PER_PAGE, limit=PER_PAGE)
    return texts.orders_list(total, page, pages), kb.orders_list(items, page, pages, settings)


@router.message(F.text == texts.BTN_ORDERS)
async def orders_message(message: Message, state: FSMContext, session: AsyncSession, user: User, settings: Settings) -> None:
    await state.clear()
    text, markup = await _orders_screen(session, user.id, 0, settings)
    await message.answer(text, reply_markup=markup)


@router.callback_query(OrdersPage.filter())
async def orders_page(call: CallbackQuery, callback_data: OrdersPage, session: AsyncSession, user: User, settings: Settings) -> None:
    text, markup = await _orders_screen(session, user.id, callback_data.page, settings)
    await show(call, text, markup)
    await call.answer()


@router.callback_query(OrderCb.filter(F.action == "view"))
async def order_view(call: CallbackQuery, callback_data: OrderCb, session: AsyncSession, user: User, settings: Settings) -> None:
    order = await orders.get_user_order(session, user.id, callback_data.id)
    if order is None:
        await call.answer("Order not found.", show_alert=True)
        return
    await show(call, texts.order_detail(order, settings), kb.order_detail(order, callback_data.page))
    await call.answer()


@router.callback_query(OrderCb.filter(F.action == "items"))
async def order_items(call: CallbackQuery, callback_data: OrderCb, session: AsyncSession, user: User, bot: Bot) -> None:
    order = await orders.get_user_order(session, user.id, callback_data.id)
    if order is None:
        await call.answer("Order not found.", show_alert=True)
        return
    await call.answer()
    await deliver_order(bot, user.id, order)
