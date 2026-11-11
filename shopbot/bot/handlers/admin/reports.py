"""Admin: statistics, inventory overview, recent orders."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopbot.bot import admin_keyboards as akb
from shopbot.bot import texts
from shopbot.bot.callbacks import Adm
from shopbot.bot.utils import clamp_page, page_count, show
from shopbot.config import Settings
from shopbot.db.models import User
from shopbot.services import inventory, orders, stats

router = Router(name="admin-reports")

INVENTORY_PER_PAGE = 25
ORDERS_PER_PAGE = 15


@router.callback_query(Adm.filter(F.act == "stats"))
async def show_stats(call: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    data = await stats.collect_stats(session)
    await show(call, texts.admin_stats(data, settings), akb.back("home", text="⬅️ Admin panel"))
    await call.answer()


@router.callback_query(Adm.filter(F.act == "inv"))
async def show_inventory(call: CallbackQuery, callback_data: Adm, session: AsyncSession, settings: Settings) -> None:
    rows = await inventory.inventory_overview(session)
    pages = page_count(len(rows), INVENTORY_PER_PAGE)
    page = clamp_page(callback_data.page, pages)
    chunk = rows[page * INVENTORY_PER_PAGE : (page + 1) * INVENTORY_PER_PAGE]
    await show(call, texts.admin_inventory(chunk, page, pages, settings), akb.inventory(page, pages))
    await call.answer()


@router.callback_query(Adm.filter(F.act == "orders"))
async def show_orders(call: CallbackQuery, callback_data: Adm, session: AsyncSession, settings: Settings) -> None:
    total = await orders.count_orders(session)
    pages = page_count(total, ORDERS_PER_PAGE)
    page = clamp_page(callback_data.page, pages)
    items = await orders.recent_orders(session, offset=page * ORDERS_PER_PAGE, limit=ORDERS_PER_PAGE)
    user_ids = {o.user_id for o in items}
    buyers = {u.id: u for u in (await session.scalars(select(User).where(User.id.in_(user_ids)))).all()} if user_ids else {}
    await show(call, texts.admin_orders(items, buyers, page, pages, settings), akb.orders(page, pages))
    await call.answer()
