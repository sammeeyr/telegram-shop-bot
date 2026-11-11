"""Catch-alls. Must be included last."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message

from shopbot.bot import keyboards as kb

router = Router(name="fallback")


@router.message(StateFilter(None))
async def unknown_message(message: Message, is_admin: bool) -> None:
    await message.answer("🤔 I didn't get that. Use the menu below 👇", reply_markup=kb.main_menu(is_admin))


@router.message()
async def unexpected_input(message: Message) -> None:
    await message.answer("⚠️ Please follow the prompt above, or send /cancel to stop.")


@router.callback_query()
async def stale_button(call: CallbackQuery) -> None:
    await call.answer("This button is no longer active.")
