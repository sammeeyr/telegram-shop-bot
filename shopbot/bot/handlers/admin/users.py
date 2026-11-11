"""Admin: user lookup, balance adjustments, bans."""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from shopbot.bot import admin_keyboards as akb
from shopbot.bot import texts
from shopbot.bot.callbacks import Adm
from shopbot.bot.filters import free_input
from shopbot.bot.states import UserAdmin
from shopbot.bot.utils import reply, show
from shopbot.config import Settings
from shopbot.db.models import User
from shopbot.money import parse_signed_money
from shopbot.services import orders, users
from shopbot.services.errors import InsufficientBalance

logger = logging.getLogger(__name__)
router = Router(name="admin-users")


async def user_screen(session: AsyncSession, target: User, settings: Settings):
    count = await orders.count_user_orders(session, target.id)
    return texts.admin_user(target, count, settings), akb.user(target)


@router.callback_query(Adm.filter(F.act == "users"))
async def users_search_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(UserAdmin.search)
    await reply(call, "🔎 Send a user's Telegram ID or @username. /cancel to abort.")
    await call.answer()


@router.message(UserAdmin.search, F.text, free_input)
async def users_search(message: Message, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    target = await users.find_user(session, message.text or "")
    if target is None:
        await message.answer("❓ User not found. They must have started the bot. Try again or /cancel.")
        return
    await state.clear()
    text, markup = await user_screen(session, target, settings)
    await message.answer(text, reply_markup=markup)


@router.callback_query(Adm.filter(F.act == "user"))
async def user_view(call: CallbackQuery, callback_data: Adm, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    await state.clear()
    target = await users.get_user(session, callback_data.id)
    if target is None:
        await call.answer("User not found.", show_alert=True)
        return
    await show(call, *await user_screen(session, target, settings))
    await call.answer()


@router.callback_query(Adm.filter(F.act == "user_bal"))
async def balance_start(call: CallbackQuery, callback_data: Adm, state: FSMContext, settings: Settings) -> None:
    await state.set_state(UserAdmin.balance)
    await state.update_data(user_id=callback_data.id)
    await reply(
        call,
        f"💰 Send the amount in {settings.currency}: <code>+10</code> to add, <code>-5</code> to deduct.\n/cancel to abort.",
    )
    await call.answer()


@router.message(UserAdmin.balance, F.text, free_input)
async def balance_input(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings, bot: Bot
) -> None:
    delta = parse_signed_money(message.text or "")
    if delta is None:
        await message.answer("⚠️ Invalid amount. Examples: <code>+10</code>, <code>-2.50</code>")
        return
    user_id = (await state.get_data())["user_id"]
    try:
        new_balance = await users.admin_adjust_balance(session, user_id, delta, admin_id=message.from_user.id)
    except InsufficientBalance as exc:
        await message.answer(f"⚠️ The user only has {settings.money(exc.balance)}. Try a smaller amount.")
        return
    await state.clear()
    logger.info("Admin %s adjusted balance of %s by %s", message.from_user.id, user_id, delta)

    if delta > 0:
        try:
            await bot.send_message(
                user_id, f"🎁 Your balance was credited with <b>{settings.money(delta)}</b>.\n"
                f"💰 New balance: <b>{settings.money(new_balance)}</b>"
            )
        except TelegramAPIError:
            pass
    target = await users.get_user(session, user_id)
    text, markup = await user_screen(session, target, settings)
    await message.answer(f"✅ Balance updated: {settings.money(new_balance)}\n\n{text}", reply_markup=markup)


@router.callback_query(Adm.filter(F.act == "user_ban"))
async def ban_toggle(call: CallbackQuery, callback_data: Adm, session: AsyncSession, settings: Settings) -> None:
    target = await users.get_user(session, callback_data.id)
    if target is None:
        await call.answer("User not found.", show_alert=True)
        return
    if settings.is_admin(target.id):
        await call.answer("You can't ban an admin.", show_alert=True)
        return
    target = await users.set_banned(session, target.id, not target.is_banned)
    await show(call, *await user_screen(session, target, settings))
    await call.answer("User banned." if target.is_banned else "User unbanned.")


@router.callback_query(Adm.filter(F.act == "user_orders"))
async def user_orders(call: CallbackQuery, callback_data: Adm, session: AsyncSession, settings: Settings) -> None:
    target = await users.get_user(session, callback_data.id)
    if target is None:
        await call.answer("User not found.", show_alert=True)
        return
    items = await orders.list_user_orders(session, target.id, offset=0, limit=20)
    await show(call, texts.admin_user_orders(target, items, settings), akb.back("user", target.id))
    await call.answer()
