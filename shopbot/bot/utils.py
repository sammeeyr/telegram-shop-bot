from __future__ import annotations

import html
from datetime import datetime

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message


def h(value: object) -> str:
    """Escape text for Telegram HTML parse mode."""
    return html.escape("" if value is None else str(value), quote=False)


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def fmt_dt(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M UTC") if value else "—"


def fmt_date(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d") if value else "—"


def user_link(user_id: int, username: str | None = None, full_name: str | None = None) -> str:
    label = f"@{username}" if username else (full_name or str(user_id))
    return f'<a href="tg://user?id={user_id}">{h(label)}</a>'


def page_count(total: int, per_page: int) -> int:
    return max(1, -(-total // per_page))


def clamp_page(page: int, pages: int) -> int:
    return min(max(page, 0), pages - 1)


async def show(call: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    """Edit the message the button belongs to, or send a new one if that's impossible."""
    message = call.message
    if isinstance(message, Message) and message.text is not None:
        try:
            await message.edit_text(text, reply_markup=reply_markup)
            return
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc):
                return
    await call.bot.send_message(call.from_user.id, text, reply_markup=reply_markup)


async def reply(call: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    """Send a new message to the user who pressed the button."""
    await call.bot.send_message(call.from_user.id, text, reply_markup=reply_markup)
