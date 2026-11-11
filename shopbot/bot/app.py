"""Bot bootstrap: wiring, startup and shutdown."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shopbot.bot.handlers import build_root_router
from shopbot.bot.middlewares import DbSessionMiddleware, UserMiddleware
from shopbot.bot.tasks import run_payment_poller
from shopbot.config import ConfigError, Settings, load_settings
from shopbot.db import create_engine, create_sessionmaker, init_db
from shopbot.payments import PaymentProviderError, PaymentService
from shopbot.payments.cryptopay import CryptoPayClient, CryptoPayProvider

logger = logging.getLogger("shopbot")


def build_dispatcher(
    settings: Settings, sessionmaker: async_sessionmaker[AsyncSession], payments: PaymentService | None
) -> Dispatcher:
    # Everything passed here is injectable into handlers by parameter name.
    dp = Dispatcher(storage=MemoryStorage(), settings=settings, sessionmaker=sessionmaker, payments=payments)
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(DbSessionMiddleware(sessionmaker))
        observer.outer_middleware(UserMiddleware())
    dp.include_router(build_root_router())
    return dp


async def set_commands(bot: Bot, settings: Settings) -> None:
    user_commands = [
        BotCommand(command="start", description="Open the shop"),
        BotCommand(command="menu", description="Main menu"),
        BotCommand(command="cancel", description="Cancel the current action"),
    ]
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())
    admin_commands = [*user_commands, BotCommand(command="admin", description="Admin panel")]
    for admin_id in settings.admin_ids:
        with contextlib.suppress(TelegramAPIError):  # admin hasn't started the bot yet
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))


async def run() -> None:
    settings = load_settings()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )

    engine = create_engine(settings.database_url)
    await init_db(engine)
    sessionmaker = create_sessionmaker(engine)

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True))
    me = await bot.get_me()
    logger.info("Starting @%s (%s)", me.username, settings.shop_name)
    if not settings.admin_ids:
        logger.warning("ADMIN_IDS is empty: nobody can open the admin panel")

    payments: PaymentService | None = None
    if settings.cryptopay_token:
        client = CryptoPayClient(settings.cryptopay_token, testnet=settings.cryptopay_testnet)
        try:
            app = await client.get_me()
            logger.info("Crypto Pay connected: app %r (%s)", app.get("name"), "testnet" if settings.cryptopay_testnet else "mainnet")
        except PaymentProviderError as exc:
            logger.error("Crypto Pay check failed (top-ups may not work): %s", exc)
        provider = CryptoPayProvider(
            client, fiat=settings.currency, accepted_assets=settings.cryptopay_assets, bot_username=me.username
        )
        payments = PaymentService(
            sessionmaker, provider, invoice_ttl_minutes=settings.invoice_ttl_minutes, shop_name=settings.shop_name
        )
    else:
        logger.warning("CRYPTOPAY_TOKEN is not set: top-ups are disabled (admins can still add balance manually)")

    dp = build_dispatcher(settings, sessionmaker, payments)
    await set_commands(bot, settings)
    poller = asyncio.create_task(run_payment_poller(bot, payments, settings)) if payments else None

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        if poller:
            poller.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await poller
        if payments:
            await payments.close()
        await bot.session.close()
        await engine.dispose()
        logger.info("Stopped")


def main() -> None:
    try:
        asyncio.run(run())
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        pass
