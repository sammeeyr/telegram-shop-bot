"""Admin: categories and products."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from shopbot.bot import admin_keyboards as akb
from shopbot.bot import texts
from shopbot.bot.callbacks import Adm
from shopbot.bot.filters import free_input
from shopbot.bot.states import CategoryForm, ProductEdit, ProductForm
from shopbot.bot.utils import h, reply, show
from shopbot.config import Settings
from shopbot.db.models import DeliveryType
from shopbot.money import parse_money
from shopbot.services import catalog

router = Router(name="admin-catalog")

EDIT_PROMPTS = {
    "edit_name": "✏️ Send the new product name.",
    "edit_desc": "✏️ Send the new description (or <code>-</code> to clear it).",
    "edit_price": "✏️ Send the new price, e.g. <code>4.99</code>.",
    "edit_static": "📝 Send the new content: a <b>file</b> (with optional caption) and/or <b>text</b> such as a download link.",
}


# ── Screens ──────────────────────────────────────────────────────────────


async def category_screen(session: AsyncSession, category_id: int, settings: Settings):
    category = await catalog.get_category(session, category_id)
    if category is None:
        return None
    views = await catalog.list_products(session, category_id, include_hidden=True)
    return texts.admin_category(category, views, settings), akb.category(category, views, settings)


async def product_screen(session: AsyncSession, product_id: int, settings: Settings):
    view = await catalog.get_product_view(session, product_id)
    if view is None:
        return None
    category = await catalog.get_category(session, view.product.category_id)
    return texts.admin_product(view, category, settings), akb.product(view)


@router.callback_query(Adm.filter(F.act == "cats"))
async def categories_list(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    items = await catalog.list_categories(session, include_hidden=True)
    await show(call, texts.admin_categories(items), akb.categories(items))
    await call.answer()


@router.callback_query(Adm.filter(F.act == "cat"))
async def category_view(call: CallbackQuery, callback_data: Adm, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    await state.clear()
    screen = await category_screen(session, callback_data.id, settings)
    if screen is None:
        await call.answer("Category not found.", show_alert=True)
        return
    await show(call, *screen)
    await call.answer()


@router.callback_query(Adm.filter(F.act == "prod"))
async def product_view(call: CallbackQuery, callback_data: Adm, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    await state.clear()
    screen = await product_screen(session, callback_data.id, settings)
    if screen is None:
        await call.answer("Product not found.", show_alert=True)
        return
    await show(call, *screen)
    await call.answer()


# ── Categories ───────────────────────────────────────────────────────────


@router.callback_query(Adm.filter(F.act.in_({"cat_new", "cat_rename"})))
async def category_name_start(call: CallbackQuery, callback_data: Adm, state: FSMContext) -> None:
    await state.set_state(CategoryForm.name)
    await state.update_data(category_id=callback_data.id if callback_data.act == "cat_rename" else None)
    await reply(call, "📂 Send the category name (max 64 chars). /cancel to abort.")
    await call.answer()


@router.message(CategoryForm.name, F.text, free_input)
async def category_name_input(message: Message, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    name = (message.text or "").strip()[:64]
    if not name:
        await message.answer("Name can't be empty.")
        return
    data = await state.get_data()
    await state.clear()
    if data.get("category_id"):
        category = await catalog.update_category(session, data["category_id"], name=name)
        if category is None:
            await message.answer("Category not found.")
            return
    else:
        category = await catalog.create_category(session, name)
    text, markup = await category_screen(session, category.id, settings)
    await message.answer(f"✅ Saved.\n\n{text}", reply_markup=markup)


@router.callback_query(Adm.filter(F.act == "cat_toggle"))
async def category_toggle(call: CallbackQuery, callback_data: Adm, session: AsyncSession, settings: Settings) -> None:
    category = await catalog.get_category(session, callback_data.id)
    if category is None:
        await call.answer("Category not found.", show_alert=True)
        return
    await catalog.update_category(session, category.id, is_active=not category.is_active)
    await show(call, *await category_screen(session, category.id, settings))
    await call.answer("Visible to shoppers." if category.is_active else "Hidden from shoppers.")


@router.callback_query(Adm.filter(F.act == "cat_del"))
async def category_delete_ask(call: CallbackQuery, callback_data: Adm, session: AsyncSession) -> None:
    category = await catalog.get_category(session, callback_data.id)
    if category is None:
        await call.answer("Category not found.", show_alert=True)
        return
    await show(
        call,
        f"🗑 Delete category <b>{h(category.name)}</b> with <b>all its products and unsold stock</b>?\n\n"
        "Order history is kept. This cannot be undone. Consider 🙈 Hide instead.",
        akb.confirm(Adm(act="cat_del_ok", id=category.id), Adm(act="cat", id=category.id)),
    )
    await call.answer()


@router.callback_query(Adm.filter(F.act == "cat_del_ok"))
async def category_delete(call: CallbackQuery, callback_data: Adm, session: AsyncSession) -> None:
    await catalog.delete_category(session, callback_data.id)
    items = await catalog.list_categories(session, include_hidden=True)
    await show(call, texts.admin_categories(items), akb.categories(items))
    await call.answer("Category deleted.")


# ── Product creation wizard ──────────────────────────────────────────────


@router.callback_query(Adm.filter(F.act == "prod_new"))
async def product_new(call: CallbackQuery, callback_data: Adm, state: FSMContext) -> None:
    await state.set_state(ProductForm.name)
    await state.update_data(category_id=callback_data.id)
    await reply(call, "🏷 <b>New product</b> (step 1/4)\n\nSend the product name (max 128 chars). /cancel to abort.")
    await call.answer()


@router.message(ProductForm.name, F.text, free_input)
async def product_new_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()[:128]
    if not name:
        await message.answer("Name can't be empty.")
        return
    await state.update_data(name=name)
    await state.set_state(ProductForm.description)
    await message.answer("📝 (step 2/4) Send the product description, or /skip.")


@router.message(ProductForm.description, Command("skip"))
@router.message(ProductForm.description, F.text, free_input)
async def product_new_description(message: Message, state: FSMContext, settings: Settings) -> None:
    text = (message.text or "").strip()
    await state.update_data(description="" if text.startswith("/skip") else text[:3000])
    await state.set_state(ProductForm.price)
    await message.answer(f"💵 (step 3/4) Send the price in {settings.currency}, e.g. <code>4.99</code>.")


@router.message(ProductForm.price, F.text, free_input)
async def product_new_price(message: Message, state: FSMContext) -> None:
    price = parse_money(message.text or "")
    if price is None:
        await message.answer("⚠️ Invalid price. Send a positive number like <code>4.99</code>.")
        return
    await state.update_data(price=price)
    await state.set_state(ProductForm.delivery_type)
    await message.answer("🚚 (step 4/4) How is this product delivered?", reply_markup=akb.delivery_type_choice())


@router.callback_query(ProductForm.delivery_type, Adm.filter(F.act == "prod_type"))
async def product_new_type(
    call: CallbackQuery, callback_data: Adm, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    if callback_data.id == 1:
        await state.set_state(ProductForm.static_content)
        await show(call, EDIT_PROMPTS["edit_static"] + "\n\n/cancel to abort.")
        await call.answer()
        return
    data = await state.get_data()
    await state.clear()
    product = await catalog.create_product(
        session, category_id=data["category_id"], name=data["name"], description=data["description"],
        price=data["price"], delivery_type=DeliveryType.STOCK,
    )
    text, markup = await product_screen(session, product.id, settings)
    await show(call, f"✅ Product created. Now tap <b>➕ Add stock</b>.\n\n{text}", markup)
    await call.answer()


def _static_content(message: Message) -> tuple[str | None, str | None]:
    file_id = message.document.file_id if message.document else None
    text = (message.caption if message.document else message.text) or None
    return (text.strip() if text else None), file_id


@router.message(ProductForm.static_content, free_input)
async def product_new_static(message: Message, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    static_text, static_file_id = _static_content(message)
    if not static_text and not static_file_id:
        await message.answer("⚠️ Send a document (file) or a text message.")
        return
    data = await state.get_data()
    await state.clear()
    product = await catalog.create_product(
        session, category_id=data["category_id"], name=data["name"], description=data["description"],
        price=data["price"], delivery_type=DeliveryType.STATIC, static_text=static_text, static_file_id=static_file_id,
    )
    text, markup = await product_screen(session, product.id, settings)
    await message.answer(f"✅ Product created.\n\n{text}", reply_markup=markup)


# ── Product editing ──────────────────────────────────────────────────────


@router.callback_query(Adm.filter(F.act.in_(set(EDIT_PROMPTS))))
async def product_edit_start(call: CallbackQuery, callback_data: Adm, state: FSMContext) -> None:
    await state.set_state(ProductEdit.value)
    await state.update_data(product_id=callback_data.id, field=callback_data.act)
    await reply(call, EDIT_PROMPTS[callback_data.act] + "\n\n/cancel to abort.")
    await call.answer()


@router.message(ProductEdit.value, free_input)
async def product_edit_value(message: Message, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    data = await state.get_data()
    field, product_id = data["field"], data["product_id"]
    text = (message.text or "").strip()

    if field == "edit_name":
        if not text:
            await message.answer("Send the name as text.")
            return
        changes = {"name": text[:128]}
    elif field == "edit_desc":
        changes = {"description": "" if text == "-" else text[:3000]}
    elif field == "edit_price":
        price = parse_money(text)
        if price is None:
            await message.answer("⚠️ Invalid price. Send a positive number like <code>4.99</code>.")
            return
        changes = {"price": price}
    else:
        static_text, static_file_id = _static_content(message)
        if not static_text and not static_file_id:
            await message.answer("⚠️ Send a document (file) or a text message.")
            return
        changes = {"static_text": static_text, "static_file_id": static_file_id}

    await state.clear()
    if await catalog.update_product(session, product_id, **changes) is None:
        await message.answer("Product not found.")
        return
    text, markup = await product_screen(session, product_id, settings)
    await message.answer(f"✅ Saved.\n\n{text}", reply_markup=markup)


@router.callback_query(Adm.filter(F.act == "prod_toggle"))
async def product_toggle(call: CallbackQuery, callback_data: Adm, session: AsyncSession, settings: Settings) -> None:
    product = await catalog.get_product(session, callback_data.id)
    if product is None:
        await call.answer("Product not found.", show_alert=True)
        return
    await catalog.update_product(session, product.id, is_active=not product.is_active)
    await show(call, *await product_screen(session, product.id, settings))
    await call.answer("Visible to shoppers." if product.is_active else "Hidden from shoppers.")


@router.callback_query(Adm.filter(F.act == "prod_del"))
async def product_delete_ask(call: CallbackQuery, callback_data: Adm, session: AsyncSession) -> None:
    product = await catalog.get_product(session, callback_data.id)
    if product is None:
        await call.answer("Product not found.", show_alert=True)
        return
    await show(
        call,
        f"🗑 Delete <b>{h(product.name)}</b> and all its unsold stock?\n\nOrder history is kept. This cannot be undone.",
        akb.confirm(Adm(act="prod_del_ok", id=product.id), Adm(act="prod", id=product.id)),
    )
    await call.answer()


@router.callback_query(Adm.filter(F.act == "prod_del_ok"))
async def product_delete(call: CallbackQuery, callback_data: Adm, session: AsyncSession, settings: Settings) -> None:
    product = await catalog.get_product(session, callback_data.id)
    if product is None:
        await call.answer("Product not found.", show_alert=True)
        return
    category_id = product.category_id
    await catalog.delete_product(session, product.id)
    screen = await category_screen(session, category_id, settings)
    if screen:
        await show(call, *screen)
    await call.answer("Product deleted.")
