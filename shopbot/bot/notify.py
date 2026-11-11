from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from shopbot.bot import keyboards as kb
from shopbot.bot import texts
from shopbot.config import Settings
from shopbot.services.deposits import CreditResult

logger = logging.getLogger(__name__)


async def notify_admins(bot: Bot, settings: Settings, text: str) -> None:
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except TelegramAPIError as exc:
            logger.warning("Could not notify admin %s: %s", admin_id, exc)


async def announce_deposit(bot: Bot, settings: Settings, credit: CreditResult, *, notify_user: bool = True) -> None:
    deposit = credit.deposit
    if notify_user:
        try:
            await bot.send_message(
                deposit.user_id,
                texts.deposit_credited_notice(deposit, credit.new_balance, settings),
                reply_markup=kb.deposit_done(),
            )
        except TelegramAPIError as exc:
            logger.warning("Could not notify user %s about deposit #%s: %s", deposit.user_id, deposit.id, exc)
    if settings.notify_admins:
        await notify_admins(bot, settings, texts.admin_deposit_paid(deposit, settings))
