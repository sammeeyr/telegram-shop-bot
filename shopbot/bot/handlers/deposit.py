"""Balance top-ups via crypto invoices."""
from __future__ import annotations

import logging
import time

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from shopbot.bot import keyboards as kb
from shopbot.bot import texts
from shopbot.bot.callbacks import DepositCb, DepositsPage, Nav, TopUpCb
from shopbot.bot.filters import free_input
from shopbot.bot.notify import announce_deposit
from shopbot.bot.states import DepositStates
from shopbot.bot.utils import clamp_page, page_count, reply, show
from shopbot.config import Settings
from shopbot.db.models import DepositStatus, User
from shopbot.money import parse_money
from shopbot.payments import PaymentProviderError, PaymentService
from shopbot.services import deposits

logger = logging.getLogger(__name__)
router = Router(name="deposit")

PER_PAGE = 10
CHECK_COOLDOWN = 3.0  # seconds between manual "check payment" presses per user
_last_check: dict[int, float] = {}


async def _create_invoice(
    session: AsyncSession, user: User, amount: int, settings: Settings, payments: PaymentService
) -> tuple[str, InlineKeyboardMarkup | None]:
    pending = await deposits.count_pending_for_user(session, user.id)
    if pending >= settings.max_pending_deposits:
        return (
            f"⚠️ You already have {pending} unpaid invoices. Pay or cancel one of them first.",
            kb.markup([kb.btn("🧾 My invoices", DepositsPage(page=0))]),
        )
    try:
        deposit = await payments.create_deposit_invoice(user.id, amount)
    except PaymentProviderError:
        logger.exception("Invoice creation failed for user %s", user.id)
        return "⚠️ The payment system is unavailable right now. Please try again in a few minutes.", None
    logger.info("Invoice #%s created: user %s, %s", deposit.id, user.id, amount)
    return texts.invoice(deposit, settings), kb.invoice(deposit, settings)


# ── Top-up menu ──────────────────────────────────────────────────────────


@router.message(F.text == texts.BTN_TOPUP)
async def topup_message(
    message: Message, state: FSMContext, user: User, settings: Settings, payments: PaymentService | None
) -> None:
    await state.clear()
    available = payments is not None
    await message.answer(texts.topup_menu(user.balance, settings, available), reply_markup=kb.topup_menu(settings, available))


@router.callback_query(Nav.filter(F.to == "topup"))
async def topup_callback(call: CallbackQuery, user: User, settings: Settings, payments: PaymentService | None) -> None:
    available = payments is not None
    await show(call, texts.topup_menu(user.balance, settings, available), kb.topup_menu(settings, available))
    await call.answer()


@router.callback_query(TopUpCb.filter(F.amount == 0))
async def custom_amount_start(call: CallbackQuery, state: FSMContext, settings: Settings, payments: PaymentService | None) -> None:
    if payments is None:
        await call.answer("Top-ups are unavailable right now.", show_alert=True)
        return
    await state.set_state(DepositStates.custom_amount)
    await reply(call, texts.custom_amount_prompt(settings))
    await call.answer()


@router.message(DepositStates.custom_amount, F.text, free_input)
async def custom_amount_input(
    message: Message, state: FSMContext, session: AsyncSession, user: User, settings: Settings,
    payments: PaymentService | None,
) -> None:
    amount = parse_money(message.text or "")
    if amount is None or not settings.min_deposit <= amount <= settings.max_deposit:
        await message.answer(
            f"⚠️ Please send a number between {settings.money(settings.min_deposit)} and "
            f"{settings.money(settings.max_deposit)}, or /cancel."
        )
        return
    await state.clear()
    if payments is None:
        await message.answer("Top-ups are unavailable right now.")
        return
    text, markup = await _create_invoice(session, user, amount, settings, payments)
    await message.answer(text, reply_markup=markup)


@router.callback_query(TopUpCb.filter(F.amount > 0))
async def preset_amount(
    call: CallbackQuery, callback_data: TopUpCb, session: AsyncSession, user: User, settings: Settings,
    payments: PaymentService | None,
) -> None:
    if payments is None:
        await call.answer("Top-ups are unavailable right now.", show_alert=True)
        return
    if not settings.min_deposit <= callback_data.amount <= settings.max_deposit:
        await call.answer("This amount is not allowed.", show_alert=True)
        return
    await call.answer("Creating invoice…")
    text, markup = await _create_invoice(session, user, callback_data.amount, settings, payments)
    await show(call, text, markup)


# ── Invoice actions ──────────────────────────────────────────────────────


@router.callback_query(DepositCb.filter(F.action == "view"))
async def deposit_view(call: CallbackQuery, callback_data: DepositCb, session: AsyncSession, user: User, settings: Settings) -> None:
    deposit = await deposits.get_deposit(session, callback_data.id)
    if deposit is None or deposit.user_id != user.id:
        await call.answer("Invoice not found.", show_alert=True)
        return
    pending = deposit.status == DepositStatus.PENDING
    await show(call, texts.deposit_status(deposit, settings), kb.invoice(deposit, settings) if pending else kb.deposit_done())
    await call.answer()


@router.callback_query(DepositCb.filter(F.action == "check"))
async def deposit_check(
    call: CallbackQuery, callback_data: DepositCb, session: AsyncSession, user: User, settings: Settings,
    payments: PaymentService | None, bot: Bot,
) -> None:
    if payments is None:
        await call.answer("Top-ups are unavailable right now.", show_alert=True)
        return
    deposit = await deposits.get_deposit(session, callback_data.id)
    if deposit is None or deposit.user_id != user.id:
        await call.answer("Invoice not found.", show_alert=True)
        return

    now = time.monotonic()
    if now - _last_check.get(user.id, 0.0) < CHECK_COOLDOWN:
        await call.answer("⏳ Please wait a few seconds before checking again.")
        return
    _last_check[user.id] = now

    try:
        result = await payments.check(deposit.id)
    except PaymentProviderError:
        logger.exception("Payment check failed for deposit #%s", deposit.id)
        await call.answer("⚠️ Couldn't reach the payment system. Try again in a moment.", show_alert=True)
        return

    deposit = result.deposit
    if result.credited is not None:
        await call.answer("✅ Payment received!")
        await show(call, texts.deposit_status(deposit, settings, result.credited.new_balance), kb.deposit_done())
        await announce_deposit(bot, settings, result.credited, notify_user=False)
    elif deposit.status == DepositStatus.PENDING:
        await call.answer(
            "⏳ Payment not received yet. If you've just paid, it's credited automatically within seconds.",
            show_alert=True,
        )
    else:
        await call.answer()
        await show(call, texts.deposit_status(deposit, settings), kb.deposit_done())


@router.callback_query(DepositCb.filter(F.action == "cancel"))
async def deposit_cancel(
    call: CallbackQuery, callback_data: DepositCb, user: User, settings: Settings, payments: PaymentService | None
) -> None:
    if payments is None or not await payments.cancel(callback_data.id, user.id):
        await call.answer("This invoice can't be cancelled (it may already be paid or expired).", show_alert=True)
        return
    await call.answer("Invoice cancelled.")
    await show(call, f"❌ Invoice #{callback_data.id} was cancelled.", kb.markup([kb.btn("💰 New top-up", Nav(to="topup"))]))


# ── History ──────────────────────────────────────────────────────────────


@router.callback_query(DepositsPage.filter())
async def deposits_history(
    call: CallbackQuery, callback_data: DepositsPage, session: AsyncSession, user: User, settings: Settings
) -> None:
    total = await deposits.count_user_deposits(session, user.id)
    pages = page_count(total, PER_PAGE)
    page = clamp_page(callback_data.page, pages)
    items = await deposits.list_user_deposits(session, user.id, offset=page * PER_PAGE, limit=PER_PAGE)
    await show(call, texts.deposits_list(items, total, page, pages, settings), kb.deposits_list(items, page, pages, settings))
    await call.answer()
