from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import Message, TelegramObject

from shopbot.bot.texts import MENU_BUTTONS


class IsAdmin(BaseFilter):
    """``is_admin`` is injected by :class:`~shopbot.bot.middlewares.UserMiddleware`."""

    async def __call__(self, event: TelegramObject, is_admin: bool = False) -> bool:
        return is_admin


def free_input(message: Message) -> bool:
    """True for regular input in a form: not a menu button and not a /command."""
    text = message.text or message.caption or ""
    return text not in MENU_BUTTONS and not text.startswith("/")
