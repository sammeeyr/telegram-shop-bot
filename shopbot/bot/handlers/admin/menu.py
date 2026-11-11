from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from shopbot.bot import admin_keyboards as akb
from shopbot.bot import texts
from shopbot.bot.callbacks import Adm
from shopbot.bot.utils import show
from shopbot.config import Settings

router = Router(name="admin-menu")


@router.message(Command("admin"))
@router.message(F.text == texts.BTN_ADMIN)
async def admin_home_message(message: Message, state: FSMContext, settings: Settings) -> None:
    await state.clear()
    await message.answer(texts.admin_home(settings), reply_markup=akb.home())


@router.callback_query(Adm.filter(F.act == "home"))
async def admin_home_callback(call: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    await state.clear()
    await show(call, texts.admin_home(settings), akb.home())
    await call.answer()
