"""Background jobs."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from shopbot.bot.notify import announce_deposit
from shopbot.config import Settings
from shopbot.payments import PaymentService

logger = logging.getLogger(__name__)


async def run_payment_poller(bot: Bot, payments: PaymentService, settings: Settings) -> None:
    """Credit paid invoices and expire stale ones, forever."""
    logger.info("Payment poller started (every %ss)", settings.payment_poll_interval)
    while True:
        try:
            for credit in await payments.sync_pending():
                await announce_deposit(bot, settings, credit)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Payment poller iteration failed")
        await asyncio.sleep(settings.payment_poll_interval)
