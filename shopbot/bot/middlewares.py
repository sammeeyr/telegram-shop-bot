from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shopbot.config import Settings
from shopbot.services import users

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class DbSessionMiddleware(BaseMiddleware):
    """Opens one DB session per update and passes it to handlers as ``session``."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self.sessionmaker = sessionmaker

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        async with self.sessionmaker() as session:
            data["session"] = session
            return await handler(event, data)


class UserMiddleware(BaseMiddleware):
    """Registers the user (their profile), blocks banned users, injects ``user`` and ``is_admin``."""

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        chat = data.get("event_chat")
        if chat is not None and chat.type != ChatType.PRIVATE:
            return None  # the shop only works in private chats

        tg_user = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return None

        session: AsyncSession = data["session"]
        settings: Settings = data["settings"]
        user, created = await users.get_or_create_user(session, tg_user.id, tg_user.username, tg_user.full_name)
        # Hand handlers a detached snapshot: a rollback inside a service (e.g. a failed
        # purchase) would otherwise expire it and make attribute access do sync IO.
        session.expunge(user)
        is_admin = settings.is_admin(tg_user.id)

        if user.is_banned and not is_admin:
            if isinstance(event, CallbackQuery):
                await event.answer("🚫 You are banned from this shop.", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("🚫 You are banned from this shop.")
            return None

        data["user"] = user
        data["is_admin"] = is_admin
        data["is_new_user"] = created
        return await handler(event, data)
