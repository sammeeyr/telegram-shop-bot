"""Sends purchased goods to the buyer."""
from __future__ import annotations

from aiogram import Bot
from aiogram.types import BufferedInputFile

from shopbot.bot.utils import h
from shopbot.db.models import DeliveryType, Order
from shopbot.services.inventory import serialize_items

MAX_INLINE_CHARS = 3500  # Telegram limit is 4096; keep headroom for markup
MAX_INLINE_ITEMS = 25


def _render_item(number: int, item: str) -> str:
    if "\n" in item:
        return f"<b>{number}.</b>\n<pre>{h(item)}</pre>"
    return f"<b>{number}.</b> <code>{h(item)}</code>"


async def deliver_order(bot: Bot, chat_id: int, order: Order) -> None:
    header = f"📦 <b>Order #{order.id}</b> · {h(order.product_name)} × {order.quantity}"
    items = order.items

    if order.delivered_file_id:
        await bot.send_document(chat_id, order.delivered_file_id, caption=header)

    if not items:
        if not order.delivered_file_id:
            await bot.send_message(chat_id, f"{header}\n\n⚠️ No content attached. Please contact support.")
        return

    if order.delivery_type == DeliveryType.STATIC:
        body = "\n\n".join(h(item) for item in items)
    else:
        body = "\n\n".join(_render_item(n, item) for n, item in enumerate(items, 1))

    if len(items) <= MAX_INLINE_ITEMS and len(header) + len(body) <= MAX_INLINE_CHARS:
        await bot.send_message(chat_id, f"{header}\n\n{body}")
        return

    document = BufferedInputFile(serialize_items(items).encode("utf-8"), filename=f"order_{order.id}.txt")
    await bot.send_document(chat_id, document, caption=f"{header}\n\nYour {len(items)} item(s) are in the attached file.")
