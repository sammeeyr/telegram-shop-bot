from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shopbot.db.models import Deposit, DepositStatus, Order, Product, StockItem, User, utcnow


@dataclass
class ShopStats:
    users_total: int = 0
    users_today: int = 0
    orders_total: int = 0
    orders_today: int = 0
    revenue_total: int = 0
    revenue_today: int = 0
    revenue_week: int = 0
    deposits_total: int = 0
    deposits_today: int = 0
    balances_total: int = 0
    products_active: int = 0
    stock_available: int = 0
    top_products: list[tuple[str, int, int]] = field(default_factory=list)  # (name, qty, revenue)


async def collect_stats(session: AsyncSession) -> ShopStats:
    now = utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)

    async def num(stmt) -> int:
        return int(await session.scalar(stmt) or 0)

    paid = Deposit.status == DepositStatus.PAID
    stats = ShopStats(
        users_total=await num(select(func.count(User.id))),
        users_today=await num(select(func.count(User.id)).where(User.created_at >= today)),
        orders_total=await num(select(func.count(Order.id))),
        orders_today=await num(select(func.count(Order.id)).where(Order.created_at >= today)),
        revenue_total=await num(select(func.sum(Order.total))),
        revenue_today=await num(select(func.sum(Order.total)).where(Order.created_at >= today)),
        revenue_week=await num(select(func.sum(Order.total)).where(Order.created_at >= week_ago)),
        deposits_total=await num(select(func.sum(Deposit.amount)).where(paid)),
        deposits_today=await num(select(func.sum(Deposit.amount)).where(paid, Deposit.paid_at >= today)),
        balances_total=await num(select(func.sum(User.balance))),
        products_active=await num(select(func.count(Product.id)).where(Product.is_active.is_(True))),
        stock_available=await num(select(func.count(StockItem.id)).where(StockItem.is_sold.is_(False))),
    )
    top = await session.execute(
        select(Order.product_name, func.sum(Order.quantity), func.sum(Order.total))
        .group_by(Order.product_name)
        .order_by(func.sum(Order.total).desc())
        .limit(5)
    )
    stats.top_products = [(name, int(qty), int(revenue)) for name, qty, revenue in top.all()]
    return stats
