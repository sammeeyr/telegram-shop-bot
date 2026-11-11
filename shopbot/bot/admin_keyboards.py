"""Admin panel keyboards."""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup

from shopbot.bot.callbacks import Adm
from shopbot.bot.keyboards import btn, markup, pager_row
from shopbot.bot.utils import truncate
from shopbot.config import Settings
from shopbot.db.models import Category, User
from shopbot.services.catalog import ProductView

HOME = Adm(act="home")


def home() -> InlineKeyboardMarkup:
    return markup(
        [btn("📂 Catalog", Adm(act="cats")), btn("📦 Inventory", Adm(act="inv"))],
        [btn("📈 Statistics", Adm(act="stats")), btn("🧾 Orders", Adm(act="orders"))],
        [btn("👥 Users", Adm(act="users")), btn("📣 Broadcast", Adm(act="bcast"))],
    )


def back(act: str, id: int = 0, text: str = "⬅️ Back") -> InlineKeyboardMarkup:
    return markup([btn(text, Adm(act=act, id=id))])


def categories(items: list[tuple[Category, int]]) -> InlineKeyboardMarkup:
    rows = [
        [btn(f"{'👁' if c.is_active else '🙈'} {truncate(c.name, 36)} · {n} products", Adm(act="cat", id=c.id))]
        for c, n in items
    ]
    rows.append([btn("➕ New category", Adm(act="cat_new"))])
    rows.append([btn("⬅️ Admin panel", HOME)])
    return markup(*rows)


def category(cat: Category, views: list[ProductView], settings: Settings) -> InlineKeyboardMarkup:
    rows = []
    for v in views:
        stock = "♾" if v.available is None else str(v.available)
        icon = "👁" if v.product.is_active else "🙈"
        rows.append([btn(
            f"{icon} {truncate(v.product.name, 28)} · {settings.money(v.product.price)} · 📦 {stock}",
            Adm(act="prod", id=v.product.id),
        )])
    rows.append([btn("➕ Add product", Adm(act="prod_new", id=cat.id))])
    rows.append([
        btn("✏️ Rename", Adm(act="cat_rename", id=cat.id)),
        btn("🙈 Hide" if cat.is_active else "👁 Show", Adm(act="cat_toggle", id=cat.id)),
        btn("🗑 Delete", Adm(act="cat_del", id=cat.id)),
    ])
    rows.append([btn("⬅️ Catalog", Adm(act="cats"))])
    return markup(*rows)


def product(view: ProductView) -> InlineKeyboardMarkup:
    p = view.product
    rows = []
    if p.is_static:
        rows.append([btn("📝 Replace content", Adm(act="edit_static", id=p.id))])
    else:
        rows.append([btn("➕ Add stock", Adm(act="stock_add", id=p.id)), btn("📤 Export stock", Adm(act="stock_export", id=p.id))])
        rows.append([btn("🧹 Clear unsold stock", Adm(act="stock_clear", id=p.id))])
    rows.append([
        btn("✏️ Name", Adm(act="edit_name", id=p.id)),
        btn("✏️ Description", Adm(act="edit_desc", id=p.id)),
        btn("✏️ Price", Adm(act="edit_price", id=p.id)),
    ])
    rows.append([
        btn("🙈 Hide" if p.is_active else "👁 Show", Adm(act="prod_toggle", id=p.id)),
        btn("🗑 Delete", Adm(act="prod_del", id=p.id)),
    ])
    rows.append([btn("⬅️ Category", Adm(act="cat", id=p.category_id))])
    return markup(*rows)


def delivery_type_choice() -> InlineKeyboardMarkup:
    return markup(
        [btn("🔑 Unique items (keys, accounts, codes)", Adm(act="prod_type", id=0))],
        [btn("♾ Same content for everyone (file / link)", Adm(act="prod_type", id=1))],
    )


def confirm(yes: Adm, no: Adm, yes_text: str = "✅ Yes, delete") -> InlineKeyboardMarkup:
    return markup([btn(yes_text, yes), btn("✖️ Cancel", no)])


def inventory(page: int, pages: int) -> InlineKeyboardMarkup:
    return markup(pager_row(page, pages, lambda p: Adm(act="inv", page=p)), [btn("⬅️ Admin panel", HOME)])


def orders(page: int, pages: int) -> InlineKeyboardMarkup:
    return markup(pager_row(page, pages, lambda p: Adm(act="orders", page=p)), [btn("⬅️ Admin panel", HOME)])


def user(u: User) -> InlineKeyboardMarkup:
    return markup(
        [btn("💰 Adjust balance", Adm(act="user_bal", id=u.id)), btn("📦 Orders", Adm(act="user_orders", id=u.id))],
        [btn("✅ Unban" if u.is_banned else "🚫 Ban", Adm(act="user_ban", id=u.id))],
        [btn("🔎 Find another user", Adm(act="users")), btn("⬅️ Admin panel", HOME)],
    )


def broadcast_confirm(count: int) -> InlineKeyboardMarkup:
    return confirm(Adm(act="bcast_go"), HOME, yes_text=f"📣 Send to {count} users")
