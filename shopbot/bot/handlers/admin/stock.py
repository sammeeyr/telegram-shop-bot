"""Admin: stock upload / export / clear."""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from shopbot.bot import admin_keyboards as akb
from shopbot.bot import texts
from shopbot.bot.callbacks import Adm
from shopbot.bot.filters import free_input
from shopbot.bot.handlers.admin.catalog import product_screen
from shopbot.bot.states import StockUpload
from shopbot.bot.utils import h, reply, show
from shopbot.config import Settings
from shopbot.services import catalog, inventory
from shopbot.services.errors import ShopError

router = Router(name="admin-stock")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@router.callback_query(Adm.filter(F.act == "stock_add"))
async def stock_add_start(call: CallbackQuery, callback_data: Adm, state: FSMContext, session: AsyncSession) -> None:
    product = await catalog.get_product(session, callback_data.id)
    if product is None or product.is_static:
        await call.answer("This product has no stock.", show_alert=True)
        return
    await state.set_state(StockUpload.items)
    await state.update_data(product_id=product.id)
    await reply(call, texts.admin_stock_prompt(product))
    await call.answer()


async def _ingest(message: Message, state: FSMContext, session: AsyncSession, raw: str, settings: Settings) -> None:
    items = inventory.parse_stock_payload(raw)
    if not items:
        await message.answer("⚠️ No items found. Send one item per line, or /cancel.")
        return
    product_id = (await state.get_data())["product_id"]
    try:
        result = await inventory.add_stock(session, product_id, items)
    except ShopError as exc:
        await state.clear()
        await message.answer(f"⚠️ {exc}")
        return
    await state.clear()
    screen = await product_screen(session, product_id, settings)
    product = await catalog.get_product(session, product_id)
    await message.answer(texts.admin_stock_added(product, result), reply_markup=screen[1] if screen else None)


@router.message(StockUpload.items, F.document)
async def stock_add_file(message: Message, state: FSMContext, session: AsyncSession, bot: Bot, settings: Settings) -> None:
    document = message.document
    if document.file_size and document.file_size > MAX_UPLOAD_BYTES:
        await message.answer("⚠️ File is too large (max 10 MB).")
        return
    buffer = await bot.download(document)
    raw = buffer.read().decode("utf-8-sig", errors="replace")
    await _ingest(message, state, session, raw, settings)


@router.message(StockUpload.items, F.text, free_input)
async def stock_add_text(message: Message, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    await _ingest(message, state, session, message.text or "", settings)


@router.callback_query(Adm.filter(F.act == "stock_export"))
async def stock_export(call: CallbackQuery, callback_data: Adm, session: AsyncSession) -> None:
    product = await catalog.get_product(session, callback_data.id)
    if product is None:
        await call.answer("Product not found.", show_alert=True)
        return
    items = await inventory.export_unsold(session, product.id)
    if not items:
        await call.answer("No unsold stock to export.", show_alert=True)
        return
    await call.answer()
    document = BufferedInputFile(inventory.serialize_items(items).encode("utf-8"), filename=f"stock_{product.id}.txt")
    await call.bot.send_document(call.from_user.id, document, caption=f"📤 {h(product.name)}: {len(items)} unsold items")


@router.callback_query(Adm.filter(F.act == "stock_clear"))
async def stock_clear_ask(call: CallbackQuery, callback_data: Adm, session: AsyncSession) -> None:
    product = await catalog.get_product(session, callback_data.id)
    if product is None:
        await call.answer("Product not found.", show_alert=True)
        return
    available = await inventory.count_available(session, product.id)
    await show(
        call,
        f"🧹 Delete all <b>{available}</b> unsold items of <b>{h(product.name)}</b>?\n\n"
        "Tip: 📤 Export them first if you might need them. Sold items are kept.",
        akb.confirm(Adm(act="stock_clear_ok", id=product.id), Adm(act="prod", id=product.id)),
    )
    await call.answer()


@router.callback_query(Adm.filter(F.act == "stock_clear_ok"))
async def stock_clear(call: CallbackQuery, callback_data: Adm, session: AsyncSession, settings: Settings) -> None:
    removed = await inventory.clear_unsold(session, callback_data.id)
    screen = await product_screen(session, callback_data.id, settings)
    if screen:
        await show(call, *screen)
    await call.answer(f"Removed {removed} items.")
