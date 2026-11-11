"""All user-facing texts (Telegram HTML)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from shopbot.bot.utils import fmt_date, fmt_dt, h, truncate, user_link
from shopbot.db.models import Category, Deposit, DepositStatus, Order, Product, User

if TYPE_CHECKING:
    from shopbot.config import Settings
    from shopbot.services.catalog import ProductView
    from shopbot.services.inventory import AddStockResult, InventoryRow
    from shopbot.services.stats import ShopStats

# ── Main menu buttons ────────────────────────────────────────────────────
BTN_SHOP = "🛍 Shop"
BTN_PROFILE = "👤 Profile"
BTN_TOPUP = "💰 Top Up"
BTN_ORDERS = "📦 My Orders"
BTN_SUPPORT = "🆘 Support"
BTN_ADMIN = "⚙️ Admin Panel"
MENU_BUTTONS = frozenset({BTN_SHOP, BTN_PROFILE, BTN_TOPUP, BTN_ORDERS, BTN_SUPPORT, BTN_ADMIN})

DEPOSIT_ICONS = {
    DepositStatus.PENDING: "⏳",
    DepositStatus.PAID: "✅",
    DepositStatus.EXPIRED: "⌛",
    DepositStatus.CANCELLED: "❌",
    DepositStatus.FAILED: "⚠️",
}


def stock_label(view: ProductView) -> str:
    if view.available is None:
        return "♾ Unlimited"
    if view.available <= 0:
        return "❌ Out of stock"
    return f"✅ {view.available} in stock"


# ── General ──────────────────────────────────────────────────────────────


def welcome(settings: Settings, user: User, is_new: bool) -> str:
    greeting = "Welcome" if is_new else "Welcome back"
    return (
        f"👋 {greeting} to <b>{h(settings.shop_name)}</b>, {h(user.full_name or 'friend')}!\n\n"
        "🛍 Browse the shop and buy digital products instantly\n"
        f"💰 Top up your balance with crypto ({h(', '.join(settings.cryptopay_assets[:4]))} …)\n"
        "⚡ Purchases are delivered automatically, right here\n\n"
        f"Your balance: <b>{settings.money(user.balance)}</b>"
    )


def support(settings: Settings) -> str:
    if not settings.support_contact:
        return "🆘 <b>Support</b>\n\nSupport contact isn't configured yet."
    return (
        "🆘 <b>Support</b>\n\n"
        f"Questions, problems with an order or a payment? Contact {h(settings.support_contact)}.\n"
        "Please include your order or invoice number."
    )


def profile(user: User, orders_count: int, settings: Settings) -> str:
    username = f"@{h(user.username)}" if user.username else "—"
    return (
        "👤 <b>Your profile</b>\n\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"👤 Username: {username}\n"
        f"📅 Member since: {fmt_date(user.created_at)}\n\n"
        f"💰 Balance: <b>{settings.money(user.balance)}</b>\n"
        f"📥 Total deposited: {settings.money(user.total_deposited)}\n"
        f"💸 Total spent: {settings.money(user.total_spent)}\n"
        f"📦 Orders: {orders_count}"
    )


# ── Shop ─────────────────────────────────────────────────────────────────


def shop_categories(has_categories: bool) -> str:
    if not has_categories:
        return "🛍 <b>Shop</b>\n\nThe shop is empty right now. Check back soon!"
    return "🛍 <b>Shop</b>\n\nChoose a category:"


def shop_category(category: Category, views: list[ProductView]) -> str:
    text = f"📂 <b>{h(category.name)}</b>"
    if category.description:
        text += f"\n{h(category.description)}"
    return text + ("\n\nChoose a product:" if views else "\n\nNo products here yet.")


def product_card(view: ProductView, balance: int, settings: Settings) -> str:
    product = view.product
    text = f"🏷 <b>{h(product.name)}</b>\n"
    if product.description:
        text += f"\n{h(truncate(product.description, 3000))}\n"
    return text + (
        f"\n💵 Price: <b>{settings.money(product.price)}</b>"
        f"\n📦 Stock: {stock_label(view)}"
        f"\n💰 Your balance: {settings.money(balance)}"
    )


def checkout(product: Product, qty: int, total: int, balance: int, settings: Settings) -> str:
    text = (
        "🛒 <b>Checkout</b>\n\n"
        f"🏷 {h(product.name)}\n"
        f"💵 {settings.money(product.price)} × {qty}\n"
        f"🧾 Total: <b>{settings.money(total)}</b>\n"
        f"💰 Your balance: {settings.money(balance)}"
    )
    if balance < total:
        text += f"\n\n⚠️ Not enough balance. You need <b>{settings.money(total - balance)}</b> more."
    return text


def purchase_success(order: Order, new_balance: int, settings: Settings) -> str:
    return (
        "✅ <b>Payment successful!</b>\n\n"
        f"🧾 Order <b>#{order.id}</b>: {h(order.product_name)} × {order.quantity}\n"
        f"💵 Paid: {settings.money(order.total)}\n"
        f"💰 New balance: <b>{settings.money(new_balance)}</b>\n\n"
        "Your purchase is below 👇 You can open it again any time from 📦 My Orders."
    )


# ── Orders ───────────────────────────────────────────────────────────────


def orders_list(total: int, page: int, pages: int) -> str:
    if total == 0:
        return "📦 <b>My orders</b>\n\nYou have no orders yet. Visit 🛍 Shop to buy something!"
    return f"📦 <b>My orders</b> ({total})\n\nTap an order to view it. Page {page + 1}/{pages}."


def order_detail(order: Order, settings: Settings) -> str:
    return (
        f"🧾 <b>Order #{order.id}</b>\n\n"
        f"🏷 {h(order.product_name)}\n"
        f"🔢 Quantity: {order.quantity}\n"
        f"💵 Unit price: {settings.money(order.unit_price)}\n"
        f"💰 Total: <b>{settings.money(order.total)}</b>\n"
        f"📅 Date: {fmt_dt(order.created_at)}"
    )


# ── Top-ups ──────────────────────────────────────────────────────────────


def topup_menu(balance: int, settings: Settings, available: bool) -> str:
    if not available:
        return (
            "💰 <b>Top up balance</b>\n\n"
            "Top-ups are temporarily unavailable. Please try again later"
            + (f" or contact {h(settings.support_contact)}." if settings.support_contact else ".")
        )
    return (
        "💰 <b>Top up balance</b>\n\n"
        f"Current balance: <b>{settings.money(balance)}</b>\n\n"
        f"🪙 Pay with crypto via @CryptoBot: {h(', '.join(settings.cryptopay_assets))}\n"
        f"📏 Min {settings.money(settings.min_deposit)} · Max {settings.money(settings.max_deposit)}\n\n"
        "Choose an amount:"
    )


def custom_amount_prompt(settings: Settings) -> str:
    return (
        f"✏️ Send the amount in {settings.currency} "
        f"({settings.money(settings.min_deposit)} – {settings.money(settings.max_deposit)}), e.g. <code>15</code>.\n\n"
        "/cancel to abort."
    )


def invoice(deposit: Deposit, settings: Settings) -> str:
    text = (
        f"🧾 <b>Invoice #{deposit.id}</b>\n\n"
        f"💵 Amount: <b>{settings.money(deposit.amount)}</b>\n"
        f"🪙 Pay with: {h(', '.join(settings.cryptopay_assets))}\n"
        f"⏳ Valid until: {fmt_dt(deposit.expires_at)}\n\n"
        "1️⃣ Tap <b>Pay</b> and complete the payment in @CryptoBot\n"
        "2️⃣ Your balance is credited automatically after payment (usually within seconds)"
    )
    if settings.cryptopay_testnet:
        text += "\n\n🧪 <i>Testnet mode: use test coins only.</i>"
    return text


def deposit_status(deposit: Deposit, settings: Settings, new_balance: int | None = None) -> str:
    status = deposit.status
    if status == DepositStatus.PAID:
        text = f"✅ <b>Payment received!</b>\n\nInvoice #{deposit.id}: +{settings.money(deposit.amount)} added to your balance."
        if new_balance is not None:
            text += f"\n💰 New balance: <b>{settings.money(new_balance)}</b>"
        return text
    if status == DepositStatus.EXPIRED:
        return f"⌛ Invoice #{deposit.id} has expired. Create a new one from 💰 Top Up."
    if status == DepositStatus.CANCELLED:
        return f"❌ Invoice #{deposit.id} was cancelled."
    if status == DepositStatus.FAILED:
        return f"⚠️ Invoice #{deposit.id} could not be created. Please try again."
    return invoice(deposit, settings)


def deposits_list(deposits: list[Deposit], total: int, page: int, pages: int, settings: Settings) -> str:
    if total == 0:
        return "🧾 <b>Top-up history</b>\n\nNo top-ups yet."
    lines = [
        f"{DEPOSIT_ICONS.get(d.status, '•')} #{d.id} · {settings.money(d.amount)} · {d.status} · {fmt_date(d.created_at)}"
        for d in deposits
    ]
    return f"🧾 <b>Top-up history</b> ({total}), page {page + 1}/{pages}\n\n" + "\n".join(lines)


def deposit_credited_notice(deposit: Deposit, new_balance: int, settings: Settings) -> str:
    return (
        f"✅ <b>Top-up received!</b>\n\n+{settings.money(deposit.amount)} (invoice #{deposit.id})\n"
        f"💰 New balance: <b>{settings.money(new_balance)}</b>"
    )


# ── Admin ────────────────────────────────────────────────────────────────


def admin_home(settings: Settings) -> str:
    return (
        f"⚙️ <b>Admin panel</b> · {h(settings.shop_name)}\n\n"
        "📂 <b>Catalog</b>: categories, products, stock\n"
        "📦 <b>Inventory</b>: stock levels at a glance\n"
        "📈 <b>Statistics</b>: revenue, users, top products\n"
        "🧾 <b>Orders</b>: recent sales\n"
        "👥 <b>Users</b>: find users, adjust balances, ban\n"
        "📣 <b>Broadcast</b>: message all users"
    )


def admin_categories(categories: list[tuple[Category, int]]) -> str:
    if not categories:
        return "📂 <b>Catalog</b>\n\nNo categories yet. Create the first one 👇"
    return f"📂 <b>Catalog</b>: {len(categories)} categories\n\n👁 visible · 🙈 hidden. Tap one to manage it."


def admin_category(category: Category, views: list[ProductView], settings: Settings) -> str:
    status = "👁 Visible" if category.is_active else "🙈 Hidden"
    text = f"📂 <b>{h(category.name)}</b> (#{category.id}) · {status}\n"
    if category.description:
        text += f"{h(category.description)}\n"
    if not views:
        return text + "\nNo products yet. Add one 👇"
    return text + f"\n{len(views)} products. Tap one to manage it."


def admin_product(view: ProductView, category: Category | None, settings: Settings) -> str:
    p = view.product
    delivery = "♾ Same content for everyone" if p.is_static else "🔑 Unique stock items"
    stock = "♾ Unlimited" if view.available is None else f"{view.available} available"
    text = (
        f"🏷 <b>{h(p.name)}</b> (#{p.id})\n\n"
        f"📂 Category: {h(category.name) if category else '—'}\n"
        f"💵 Price: <b>{settings.money(p.price)}</b>\n"
        f"🚚 Delivery: {delivery}\n"
        f"📦 Stock: {stock} · {view.sold} sold\n"
        f"👁 Status: {'Visible' if p.is_active else '🙈 Hidden'}\n"
    )
    if p.is_static:
        content = []
        if p.static_file_id:
            content.append("📎 file")
        if p.static_text:
            content.append(f"📝 text ({len(p.static_text)} chars)")
        text += f"📄 Content: {', '.join(content) if content else '⚠️ not set'}\n"
    if p.description:
        text += f"\n{h(truncate(p.description, 1500))}"
    return text


def admin_stock_prompt(product: Product) -> str:
    return (
        f"➕ <b>Add stock to {h(product.name)}</b>\n\n"
        "Send items as a message or upload a <b>.txt</b> file:\n"
        "• one item per line, <i>or</i>\n"
        "• for multi-line items, separate them with a line containing only <code>---</code>\n\n"
        "Duplicates (including already-sold items) are skipped automatically.\n/cancel to abort."
    )


def admin_stock_added(product: Product, result: AddStockResult) -> str:
    text = f"✅ Added <b>{result.added}</b> items to <b>{h(product.name)}</b>."
    if result.duplicates:
        text += f"\n♻️ Skipped {result.duplicates} duplicates."
    return text + f"\n📦 Available now: <b>{result.available}</b>"


def admin_inventory(rows: list[InventoryRow], page: int, pages: int, settings: Settings) -> str:
    if not rows:
        return "📦 <b>Inventory</b>\n\nNo products yet."
    lines = []
    for row in rows:
        if row.available is None:
            level = "♾"
        elif row.available == 0:
            level = "❌ 0"
        elif row.available <= settings.low_stock_threshold:
            level = f"⚠️ {row.available}"
        else:
            level = f"✅ {row.available}"
        hidden = " 🙈" if not row.product.is_active else ""
        lines.append(
            f"{level} · <b>{h(truncate(row.product.name, 40))}</b>{hidden}\n"
            f"      {h(row.category_name)} · {settings.money(row.product.price)} · {row.sold} sold"
        )
    return (
        f"📦 <b>Inventory</b> (page {page + 1}/{pages})\n"
        f"⚠️ = at or below {settings.low_stock_threshold} left\n\n" + "\n".join(lines)
    )


def admin_stats(stats: ShopStats, settings: Settings) -> str:
    m = settings.money
    text = (
        "📈 <b>Shop statistics</b>\n\n"
        f"👥 Users: <b>{stats.users_total}</b> (+{stats.users_today} today)\n"
        f"🧾 Orders: <b>{stats.orders_total}</b> (+{stats.orders_today} today)\n\n"
        f"💵 Revenue: <b>{m(stats.revenue_total)}</b>\n"
        f"      today {m(stats.revenue_today)} · 7 days {m(stats.revenue_week)}\n"
        f"📥 Deposits: <b>{m(stats.deposits_total)}</b> (today {m(stats.deposits_today)})\n"
        f"💰 Unspent user balances: {m(stats.balances_total)}\n\n"
        f"🏷 Active products: {stats.products_active}\n"
        f"📦 Stock items available: {stats.stock_available}"
    )
    if stats.top_products:
        text += "\n\n🏆 <b>Top products</b>\n" + "\n".join(
            f"{i}. {h(truncate(name, 40))} · {qty} sold · {m(revenue)}"
            for i, (name, qty, revenue) in enumerate(stats.top_products, 1)
        )
    return text


def admin_orders(orders: list[Order], users_by_id: dict[int, User], page: int, pages: int, settings: Settings) -> str:
    if not orders:
        return "🧾 <b>Recent orders</b>\n\nNo orders yet."
    lines = []
    for o in orders:
        u = users_by_id.get(o.user_id)
        who = user_link(o.user_id, u.username if u else None, u.full_name if u else None)
        lines.append(
            f"<b>#{o.id}</b> · {fmt_dt(o.created_at)}\n"
            f"      {who} · {h(truncate(o.product_name, 30))} × {o.quantity} · {settings.money(o.total)}"
        )
    return f"🧾 <b>Recent orders</b> (page {page + 1}/{pages})\n\n" + "\n".join(lines)


def admin_user(user: User, orders_count: int, settings: Settings) -> str:
    return (
        f"👤 <b>User</b> {user_link(user.id, user.username, user.full_name)}\n\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"📛 Name: {h(user.full_name) or '—'}\n"
        f"💰 Balance: <b>{settings.money(user.balance)}</b>\n"
        f"📥 Deposited: {settings.money(user.total_deposited)}\n"
        f"💸 Spent: {settings.money(user.total_spent)}\n"
        f"📦 Orders: {orders_count}\n"
        f"📅 Joined: {fmt_dt(user.created_at)}\n"
        f"👀 Last seen: {fmt_dt(user.last_seen_at)}\n"
        f"🚫 Banned: {'yes' if user.is_banned else 'no'}"
    )


def admin_user_orders(user: User, orders: list[Order], settings: Settings) -> str:
    if not orders:
        return f"📦 {user_link(user.id, user.username, user.full_name)} has no orders."
    lines = [
        f"#{o.id} · {fmt_date(o.created_at)} · {h(truncate(o.product_name, 30))} × {o.quantity} · {settings.money(o.total)}"
        for o in orders
    ]
    return f"📦 Last orders of {user_link(user.id, user.username, user.full_name)}\n\n" + "\n".join(lines)


def admin_new_order(order: Order, user: User, settings: Settings) -> str:
    return (
        f"🛒 <b>New order #{order.id}</b>\n"
        f"{user_link(user.id, user.username, user.full_name)} bought {h(order.product_name)} × {order.quantity} "
        f"for <b>{settings.money(order.total)}</b>"
    )


def admin_deposit_paid(deposit: Deposit, settings: Settings) -> str:
    paid = f" ({h(deposit.paid_amount)} {h(deposit.paid_asset)})" if deposit.paid_asset else ""
    return (
        f"💰 <b>Top-up #{deposit.id} paid</b>\n"
        f"{user_link(deposit.user_id)} +{settings.money(deposit.amount)}{paid}"
    )


def admin_low_stock(product_name: str, remaining: int) -> str:
    if remaining <= 0:
        return f"❌ <b>Out of stock:</b> {h(product_name)}. Add stock from ⚙️ Admin → 📂 Catalog."
    return f"⚠️ <b>Low stock:</b> {h(product_name)}, only <b>{remaining}</b> left."
