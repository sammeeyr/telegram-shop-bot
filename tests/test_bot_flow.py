"""End-to-end: feed fake Telegram updates through the real dispatcher.

A fake Bot API session records every outgoing request and validates that all
HTML sent to Telegram is well-formed and uses only supported tags.
"""
from __future__ import annotations

import itertools
import json
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, AsyncGenerator

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendDocument, SendMessage, TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message, Update
from aiogram.types import User as TgUser

import shopbot.bot.handlers.deposit as deposit_handlers
from shopbot.bot import texts
from shopbot.bot.app import build_dispatcher
from shopbot.bot.callbacks import Adm, BuyCb, CategoryCb, DepositCb, OrderCb, ProductCb, QtyCb, TopUpCb
from shopbot.bot.delivery import deliver_order
from shopbot.config import Settings
from shopbot.db.models import DepositStatus, Order, User
from shopbot.payments import InvoiceStatus, PaymentService
from tests.test_payments import FakeProvider

ADMIN, BUYER, TROLL = 1, 2, 3
ALLOWED_TAGS = {"b", "i", "u", "s", "code", "pre", "a", "tg-spoiler", "blockquote"}


class HtmlChecker(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []

    def handle_starttag(self, tag, attrs):
        assert tag in ALLOWED_TAGS, f"unsupported tag <{tag}>"
        self.stack.append(tag)

    def handle_endtag(self, tag):
        assert self.stack and self.stack[-1] == tag, f"unbalanced </{tag}>"
        self.stack.pop()


def check_html(text: str | None) -> None:
    if not text:
        return
    checker = HtmlChecker()
    checker.feed(text)
    checker.close()
    assert not checker.stack, f"unclosed tags {checker.stack} in {text!r}"


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod] = []
        self._ids = itertools.count(1000)

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:
        self.calls.append(method)
        check_html(getattr(method, "text", None))
        check_html(getattr(method, "caption", None))
        if isinstance(method, (SendMessage, EditMessageText, SendDocument)):
            chat_id = int(method.chat_id or 0)
            return Message(
                message_id=next(self._ids), date=datetime.now(), chat=Chat(id=chat_id, type="private"),
                text=getattr(method, "text", None),
            )
        return True

    async def stream_content(self, *args, **kwargs) -> AsyncGenerator[bytes, None]:
        yield b""

    async def close(self) -> None:
        pass

    def pop(self) -> list[TelegramMethod]:
        calls, self.calls = self.calls, []
        return calls


def tg_user(uid: int) -> TgUser:
    return TgUser(id=uid, is_bot=False, first_name=f"User{uid}", username=f"user{uid}")


class Client:
    """Tiny helper to simulate one Telegram user talking to the bot."""

    _ids = itertools.count(1)

    def __init__(self, dp, bot: Bot, session: FakeSession, uid: int) -> None:
        self.dp, self.bot, self.session, self.uid = dp, bot, session, uid

    def _message(self, text: str) -> Message:
        return Message(
            message_id=next(self._ids), date=datetime.now(), chat=Chat(id=self.uid, type="private"),
            from_user=tg_user(self.uid), text=text,
        )

    async def send(self, text: str) -> list[TelegramMethod]:
        await self.dp.feed_update(self.bot, Update(update_id=next(self._ids), message=self._message(text)))
        return self.session.pop()

    async def press(self, data) -> list[TelegramMethod]:
        call = CallbackQuery(
            id=str(next(self._ids)), from_user=tg_user(self.uid), chat_instance="ci",
            message=self._message("previous screen"), data=data.pack(),
        )
        await self.dp.feed_update(self.bot, Update(update_id=next(self._ids), callback_query=call))
        return self.session.pop()


def texts_of(calls: list[TelegramMethod]) -> str:
    out = []
    for c in calls:
        out.append(getattr(c, "text", None) or getattr(c, "caption", None) or "")
    return "\n".join(out)


def alerts(calls: list[TelegramMethod]) -> str:
    return "\n".join(c.text or "" for c in calls if isinstance(c, AnswerCallbackQuery))


async def test_delivery_inline_vs_file():
    session = FakeSession()
    bot = Bot("42:TEST", session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    small = Order(id=1, product_name="Acc <x>", quantity=2, delivery_type="stock",
                  delivered_items=json.dumps(["login: a\npass: <1>", "KEY&2"]))
    await deliver_order(bot, 5, small)
    assert isinstance(session.calls[-1], SendMessage) and "<pre>login: a\npass: &lt;1&gt;</pre>" in session.calls[-1].text

    big = Order(id=2, product_name="Keys", quantity=40, delivery_type="stock",
                delivered_items=json.dumps([f"KEY-{i}" for i in range(40)]))
    await deliver_order(bot, 5, big)
    assert isinstance(session.calls[-1], SendDocument) and session.calls[-1].document.filename == "order_2.txt"
    await bot.session.close()


async def test_full_shop_flow(sessionmaker):
    settings = Settings(bot_token="42:TEST", admin_ids=frozenset({ADMIN}), shop_name="Test <Shop>")
    provider = FakeProvider()
    payments = PaymentService(sessionmaker, provider, invoice_ttl_minutes=60, shop_name=settings.shop_name)
    dp = build_dispatcher(settings, sessionmaker, payments)
    session = FakeSession()
    bot = Bot("42:TEST", session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    admin = Client(dp, bot, session, ADMIN)
    buyer = Client(dp, bot, session, BUYER)
    troll = Client(dp, bot, session, TROLL)

    # Registration / profile
    assert "Welcome" in texts_of(await buyer.send("/start"))
    assert "Test &lt;Shop&gt;" in texts_of(await admin.send("/start"))
    assert "Your profile" in texts_of(await buyer.send(texts.BTN_PROFILE))
    assert "The shop is empty" in texts_of(await buyer.send(texts.BTN_SHOP))

    # Non-admins can't use the admin panel
    assert "Admin panel" not in texts_of(await buyer.send("/admin"))
    assert "no longer active" in alerts(await buyer.press(Adm(act="home")))

    # Admin: create category + product + stock
    assert "Admin panel" in texts_of(await admin.send(texts.BTN_ADMIN))
    await admin.press(Adm(act="cat_new"))
    assert "Saved" in texts_of(await admin.send("Game <Keys>"))
    await admin.press(Adm(act="prod_new", id=1))
    await admin.send("Steam Key")
    await admin.send("/skip")
    assert "Invalid price" in texts_of(await admin.send("free"))
    assert "delivered" in texts_of(await admin.send("5"))
    assert "Product created" in texts_of(await admin.press(Adm(act="prod_type", id=0)))
    await admin.press(Adm(act="stock_add", id=1))
    added = texts_of(await admin.send("KEY-1\nKEY-2\nKEY-3\nKEY-3"))
    assert "Added <b>3</b>" in added and "Skipped 1 duplicates" in added

    # Buyer can't afford it yet
    assert "Game &lt;Keys&gt;" in texts_of(await buyer.press(CategoryCb(id=1)))
    assert "3 in stock" in texts_of(await buyer.press(ProductCb(id=1)))
    assert "Not enough balance" in texts_of(await buyer.press(QtyCb(id=1, qty=2)))
    assert "Not enough balance" in alerts(await buyer.press(BuyCb(id=1, qty=2, price=500)))

    # Admin credits the buyer
    await admin.press(Adm(act="user_bal", id=BUYER))
    credited = await admin.send("+20")
    assert "Balance updated: $20.00" in texts_of(credited)
    assert any(isinstance(c, SendMessage) and c.chat_id == BUYER for c in credited)  # buyer notified

    # Stale price is rejected, correct price buys and delivers
    assert "price has changed" in alerts(await buyer.press(BuyCb(id=1, qty=2, price=400)))
    bought = await buyer.press(BuyCb(id=1, qty=2, price=500))
    out = texts_of(bought)
    assert "Payment successful" in out and "KEY-1" in out and "KEY-2" in out and "KEY-3" not in out
    assert any(c.chat_id == ADMIN and "New order" in (c.text or "") for c in bought if isinstance(c, SendMessage))
    assert any(c.chat_id == ADMIN and "Low stock" in (c.text or "") for c in bought if isinstance(c, SendMessage))
    assert "KEY-1" in texts_of(await buyer.press(OrderCb(id=1, action="items")))
    orders_screen = (await buyer.send(texts.BTN_ORDERS))[0]
    assert orders_screen.reply_markup.inline_keyboard[0][0].text.startswith("#1 · Steam Key ×2")

    # Top-up via crypto invoice, confirmed with the "I've paid" button
    assert "Top up balance" in texts_of(await buyer.send(texts.BTN_TOPUP))
    invoice = texts_of(await buyer.press(TopUpCb(amount=1000)))
    assert "Invoice #1" in invoice
    assert "not received yet" in alerts(await buyer.press(DepositCb(id=1, action="check")))
    provider.set_status("1001", InvoiceStatus.PAID)
    deposit_handlers._last_check.clear()  # skip the anti-spam cooldown
    paid = texts_of(await buyer.press(DepositCb(id=1, action="check")))
    assert "Payment received" in paid and "$20.00" in paid  # 20 - 10 spent + 10 deposited

    # Custom amount validation
    await buyer.press(TopUpCb(amount=0))
    assert "Please send a number" in texts_of(await buyer.send("0.001"))
    assert "Invoice #2" in texts_of(await buyer.send("12.5"))
    async with sessionmaker() as s:
        assert (await s.get(User, BUYER)).balance == 2000

    # Menu buttons escape a form
    await buyer.press(TopUpCb(amount=0))
    assert "Your profile" in texts_of(await buyer.send(texts.BTN_PROFILE))

    # Ban
    await troll.send("/start")
    await admin.press(Adm(act="user_ban", id=TROLL))
    assert "banned" in texts_of(await troll.send("/start"))
    assert "can't ban an admin" in alerts(await admin.press(Adm(act="user_ban", id=ADMIN)))

    # Admin reports render
    assert "Shop statistics" in texts_of(await admin.press(Adm(act="stats")))
    assert "Inventory" in texts_of(await admin.press(Adm(act="inv")))
    assert "Recent orders" in texts_of(await admin.press(Adm(act="orders")))

    # Static product: file/link delivered to everyone, quantity 1
    await admin.press(Adm(act="prod_new", id=1))
    await admin.send("E-book")
    await admin.send("A great <book>")
    await admin.send("3")
    await admin.press(Adm(act="prod_type", id=1))
    assert "Product created" in texts_of(await admin.send("https://example.com/book.pdf"))
    bought = texts_of(await buyer.press(BuyCb(id=2, qty=1, price=300)))
    assert "https://example.com/book.pdf" in bought

    # Unknown input falls back to the menu
    assert "didn't get that" in texts_of(await buyer.send("hello?"))

    # Cancelling an unpaid invoice
    assert "was cancelled" in texts_of(await buyer.press(DepositCb(id=2, action="cancel")))
    assert (await payments.check(2)).deposit.status == DepositStatus.CANCELLED
    await bot.session.close()
