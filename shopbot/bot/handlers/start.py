"""/start, main menu, profile, support, cancel."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from shopbot.bot import keyboards as kb
from shopbot.bot import texts
from shopbot.bot.callbacks import Nav
from shopbot.bot.utils import show
from shopbot.config import Settings
from shopbot.db.models import User
from shopbot.services import orders

router = Router(name="start")


@router.message(CommandStart())
@router.message(Command("menu"))
async def cmd_start(
    message: Message, state: FSMContext, user: User, settings: Settings, is_admin: bool, is_new_user: bool
) -> None:
    await state.clear()
    await message.answer(texts.welcome(settings, user, is_new_user), reply_markup=kb.main_menu(is_admin))


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, is_admin: bool) -> None:
    had_state = await state.get_state() is not None
    await state.clear()
    await message.answer("❌ Cancelled." if had_state else "Nothing to cancel.", reply_markup=kb.main_menu(is_admin))


@router.message(F.text == texts.BTN_PROFILE)
async def profile_message(message: Message, state: FSMContext, session: AsyncSession, user: User, settings: Settings) -> None:
    await state.clear()
    count = await orders.count_user_orders(session, user.id)
    await message.answer(texts.profile(user, count, settings), reply_markup=kb.profile())


@router.callback_query(Nav.filter(F.to == "profile"))
async def profile_callback(call: CallbackQuery, session: AsyncSession, user: User, settings: Settings) -> None:
    count = await orders.count_user_orders(session, user.id)
    await show(call, texts.profile(user, count, settings), kb.profile())
    await call.answer()


@router.message(F.text == texts.BTN_SUPPORT)
async def support(message: Message, state: FSMContext, settings: Settings) -> None:
    await state.clear()
    await message.answer(texts.support(settings))


@router.callback_query(Nav.filter(F.to == "noop"))
async def noop(call: CallbackQuery) -> None:
    await call.answer()
