"""Categories and products."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shopbot.db.models import Category, DeliveryType, Order, Product, StockItem, utcnow


@dataclass
class ProductView:
    product: Product
    available: int | None  # None = unlimited (static delivery)
    sold: int = 0

    @property
    def in_stock(self) -> bool:
        return self.available is None or self.available > 0


# ── Queries ──────────────────────────────────────────────────────────────


async def available_counts(session: AsyncSession, product_ids: Iterable[int]) -> dict[int, int]:
    ids = list(product_ids)
    if not ids:
        return {}
    rows = await session.execute(
        select(StockItem.product_id, func.count())
        .where(StockItem.product_id.in_(ids), StockItem.is_sold.is_(False))
        .group_by(StockItem.product_id)
    )
    counts = {pid: 0 for pid in ids}
    counts.update({pid: n for pid, n in rows.all()})
    return counts


async def sold_counts(session: AsyncSession, product_ids: Iterable[int]) -> dict[int, int]:
    ids = list(product_ids)
    if not ids:
        return {}
    rows = await session.execute(
        select(Order.product_id, func.coalesce(func.sum(Order.quantity), 0))
        .where(Order.product_id.in_(ids))
        .group_by(Order.product_id)
    )
    counts = {pid: 0 for pid in ids}
    counts.update({pid: int(n) for pid, n in rows.all()})
    return counts


async def _views(session: AsyncSession, products: list[Product]) -> list[ProductView]:
    ids = [p.id for p in products]
    available = await available_counts(session, ids)
    sold = await sold_counts(session, ids)
    return [
        ProductView(p, None if p.is_static else available.get(p.id, 0), sold.get(p.id, 0)) for p in products
    ]


async def list_categories(session: AsyncSession, *, include_hidden: bool = False) -> list[tuple[Category, int]]:
    """Categories with their product counts. For shoppers, empty/hidden ones are skipped."""
    count_q = select(func.count(Product.id)).where(Product.category_id == Category.id)
    if not include_hidden:
        count_q = count_q.where(Product.is_active.is_(True))
    stmt = select(Category, count_q.correlate(Category).scalar_subquery()).order_by(Category.sort_order, Category.id)
    if not include_hidden:
        stmt = stmt.where(Category.is_active.is_(True))
    rows = (await session.execute(stmt)).all()
    return [(c, n) for c, n in rows if include_hidden or n > 0]


async def get_category(session: AsyncSession, category_id: int) -> Category | None:
    return await session.get(Category, category_id)


async def list_products(
    session: AsyncSession, category_id: int, *, include_hidden: bool = False
) -> list[ProductView]:
    stmt = select(Product).where(Product.category_id == category_id).order_by(Product.sort_order, Product.id)
    if not include_hidden:
        stmt = stmt.where(Product.is_active.is_(True))
    products = list((await session.scalars(stmt)).all())
    return await _views(session, products)


async def get_product(session: AsyncSession, product_id: int) -> Product | None:
    return await session.get(Product, product_id)


async def get_product_view(session: AsyncSession, product_id: int) -> ProductView | None:
    product = await session.get(Product, product_id, populate_existing=True)
    if product is None:
        return None
    return (await _views(session, [product]))[0]


async def get_visible_product_view(session: AsyncSession, product_id: int) -> ProductView | None:
    """Product view only if the product and its category are visible to shoppers."""
    view = await get_product_view(session, product_id)
    if view is None or not view.product.is_active:
        return None
    category = await session.get(Category, view.product.category_id)
    if category is None or not category.is_active:
        return None
    return view


# ── Mutations ────────────────────────────────────────────────────────────


async def create_category(session: AsyncSession, name: str, description: str = "") -> Category:
    category = Category(name=name[:64], description=description, sort_order=0, is_active=True, created_at=utcnow())
    session.add(category)
    await session.commit()
    return category


async def update_category(session: AsyncSession, category_id: int, **fields) -> Category | None:
    category = await session.get(Category, category_id)
    if category is None:
        return None
    for key, value in fields.items():
        setattr(category, key, value)
    await session.commit()
    return category


async def delete_category(session: AsyncSession, category_id: int) -> bool:
    category = await session.get(Category, category_id)
    if category is None:
        return False
    product_ids = list((await session.scalars(select(Product.id).where(Product.category_id == category_id))).all())
    await _delete_products(session, product_ids)
    await session.delete(category)
    await session.commit()
    return True


async def create_product(
    session: AsyncSession,
    *,
    category_id: int,
    name: str,
    description: str,
    price: int,
    delivery_type: DeliveryType,
    static_text: str | None = None,
    static_file_id: str | None = None,
) -> Product:
    product = Product(
        category_id=category_id,
        name=name[:128],
        description=description,
        price=price,
        delivery_type=delivery_type,
        static_text=static_text,
        static_file_id=static_file_id,
        is_active=True,
        low_stock_alerted=False,
        sort_order=0,
        created_at=utcnow(),
    )
    session.add(product)
    await session.commit()
    return product


async def update_product(session: AsyncSession, product_id: int, **fields) -> Product | None:
    product = await session.get(Product, product_id)
    if product is None:
        return None
    for key, value in fields.items():
        setattr(product, key, value)
    await session.commit()
    return product


async def delete_product(session: AsyncSession, product_id: int) -> bool:
    product = await session.get(Product, product_id)
    if product is None:
        return False
    await _delete_products(session, [product_id])
    await session.commit()
    return True


async def _delete_products(session: AsyncSession, product_ids: list[int]) -> None:
    """Delete products and their stock. Orders keep their snapshot and lose only the link."""
    if not product_ids:
        return
    await session.execute(
        update(Order).where(Order.product_id.in_(product_ids)).values(product_id=None)
        .execution_options(synchronize_session=False)
    )
    await session.execute(
        delete(StockItem).where(StockItem.product_id.in_(product_ids)).execution_options(synchronize_session=False)
    )
    await session.execute(
        delete(Product).where(Product.id.in_(product_ids)).execution_options(synchronize_session=False)
    )
