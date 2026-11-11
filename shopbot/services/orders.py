"""Purchasing and order history."""
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shopbot.db.models import Category, Order, Product, StockItem, utcnow
from shopbot.services.errors import InvalidQuantity, OutOfStock, PriceChanged, ProductUnavailable, ShopError
from shopbot.services.locks import money_lock
from shopbot.services.users import change_balance


@dataclass
class PurchaseResult:
    order: Order
    new_balance: int


async def purchase(
    session: AsyncSession,
    *,
    user_id: int,
    product_id: int,
    quantity: int,
    max_quantity: int,
    expected_unit_price: int | None = None,
) -> PurchaseResult:
    """Charge the user, reserve stock and create the order in one transaction.

    Safe against double-spending and overselling: the balance is charged with a
    conditional UPDATE (balance >= total) and stock items are claimed with a
    conditional UPDATE (is_sold = false); any mismatch rolls everything back.
    """
    async with money_lock():
        try:
            return await _purchase(session, user_id, product_id, quantity, max_quantity, expected_unit_price)
        except Exception:
            await session.rollback()
            raise


async def _purchase(
    session: AsyncSession,
    user_id: int,
    product_id: int,
    quantity: int,
    max_quantity: int,
    expected_unit_price: int | None,
) -> PurchaseResult:
    product = await session.get(Product, product_id, populate_existing=True)
    if product is None or not product.is_active:
        raise ProductUnavailable()
    category = await session.get(Category, product.category_id)
    if category is None or not category.is_active:
        raise ProductUnavailable()

    limit = 1 if product.is_static else max_quantity
    if quantity < 1 or quantity > limit:
        raise InvalidQuantity(f"Quantity must be between 1 and {limit}.")
    if expected_unit_price is not None and product.price != expected_unit_price:
        raise PriceChanged()

    total = product.price * quantity
    stock_ids: list[int] = []
    if product.is_static:
        items = [product.static_text] if product.static_text else []
    else:
        rows = (
            await session.execute(
                select(StockItem.id, StockItem.content)
                .where(StockItem.product_id == product.id, StockItem.is_sold.is_(False))
                .order_by(StockItem.id)
                .limit(quantity)
            )
        ).all()
        if len(rows) < quantity:
            raise OutOfStock(len(rows))
        stock_ids = [row.id for row in rows]
        items = [row.content for row in rows]

    now = utcnow()
    order = Order(
        user_id=user_id,
        product_id=product.id,
        product_name=product.name,
        delivery_type=product.delivery_type,
        quantity=quantity,
        unit_price=product.price,
        total=total,
        delivered_items=json.dumps(items, ensure_ascii=False),
        delivered_file_id=product.static_file_id if product.is_static else None,
        created_at=now,
    )
    session.add(order)
    await session.flush()

    new_balance = await change_balance(
        session, user_id, -total, kind="purchase", reference=f"order:{order.id}", count_as_spent=True
    )

    if stock_ids:
        claimed = await session.execute(
            update(StockItem)
            .where(StockItem.id.in_(stock_ids), StockItem.is_sold.is_(False))
            .values(is_sold=True, order_id=order.id, sold_at=now)
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != len(stock_ids):
            raise ShopError("Stock just changed, please try again.")

    await session.commit()
    return PurchaseResult(order=order, new_balance=new_balance)


async def count_user_orders(session: AsyncSession, user_id: int) -> int:
    return int(await session.scalar(select(func.count(Order.id)).where(Order.user_id == user_id)) or 0)


async def list_user_orders(session: AsyncSession, user_id: int, *, offset: int, limit: int) -> list[Order]:
    stmt = select(Order).where(Order.user_id == user_id).order_by(Order.id.desc()).offset(offset).limit(limit)
    return list((await session.scalars(stmt)).all())


async def get_user_order(session: AsyncSession, user_id: int, order_id: int) -> Order | None:
    order = await session.get(Order, order_id)
    if order is None or order.user_id != user_id:
        return None
    return order


async def count_orders(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count(Order.id))) or 0)


async def recent_orders(session: AsyncSession, *, offset: int, limit: int) -> list[Order]:
    stmt = select(Order).order_by(Order.id.desc()).offset(offset).limit(limit)
    return list((await session.scalars(stmt)).all())
