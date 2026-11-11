"""Admin: broadcast a message to every (non-banned) user."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shopbot.bot import admin_keyboards as akb
from shopbot.bot.callbacks import Adm
from shopbot.bot.filters import free_input
from shopbot.bot.states import BroadcastForm
from shopbot.bot.utils import reply, show
from shopbot.services import users

logger = logging.getLogger(__name__)
router = Router(name="admin-broadcast")

SEND_DELAY = 0.05  # ~20 msgs/sec, under Telegram's global limit
_running: set[asyncio.Task] = set()


@router.callback_query(Adm.filter(F.act == "bcast"))
async def broadcast_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BroadcastForm.message)
    await reply(
        call,
        "📣 Send the message to broadcast: text, photo, video, file… It's copied to every user as-is.\n/cancel to abort.",
    )
    await call.answer()


@router.message(BroadcastForm.message, free_input)
async def broadcast_preview(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.update_data(chat_id=message.chat.id, message_id=message.message_id)
    await state.set_state(BroadcastForm.confirm)
    count = len(await users.active_user_ids(session))
    await message.reply(f"👆 Send this to <b>{count}</b> users?", reply_markup=akb.broadcast_confirm(count))


@router.callback_query(BroadcastForm.confirm, Adm.filter(F.act == "bcast_go"))
async def broadcast_go(
    call: CallbackQuery, state: FSMContext, bot: Bot, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    data = await state.get_data()
    await state.clear()
    await show(call, "📣 Broadcast started. I'll report when it's done.")
    await call.answer()
    task = asyncio.create_task(_broadcast(bot, sessionmaker, call.from_user.id, data["chat_id"], data["message_id"]))
    _running.add(task)
    task.add_done_callback(_running.discard)


async def _broadcast(bot: Bot, sessionmaker: async_sessionmaker[AsyncSession], admin_id: int, chat_id: int, message_id: int) -> None:
    async with sessionmaker() as session:
        recipients = await users.active_user_ids(session)
    sent = failed = 0
    for user_id in recipients:
        for attempt in range(2):
            try:
                await bot.copy_message(user_id, chat_id, message_id)
                sent += 1
                break
            except TelegramRetryAfter as exc:
                if attempt == 1:
                    failed += 1
                    break
                await asyncio.sleep(exc.retry_after + 1)
            except TelegramAPIError:  # blocked the bot, deleted account, …
                failed += 1
                break
        await asyncio.sleep(SEND_DELAY)
    logger.info("Broadcast finished: %s sent, %s failed", sent, failed)
    try:
        await bot.send_message(admin_id, f"📣 Broadcast finished: ✅ {sent} delivered, ❌ {failed} failed.")
    except TelegramAPIError:
        pass
