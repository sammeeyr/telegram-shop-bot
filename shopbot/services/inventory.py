"""Stock management: uploading, exporting, clearing and low-stock tracking."""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shopbot.db.models import Category, DeliveryType, Product, StockItem, utcnow
from shopbot.services.catalog import available_counts, sold_counts
from shopbot.services.errors import NotFound, ShopError

_SEPARATOR_RE = re.compile(r"^[ \t]*-{3,}[ \t]*$", re.MULTILINE)


def parse_stock_payload(text: str) -> list[str]:
    """Split uploaded stock into items.

    * Default: one item per line.
    * If the text contains separator lines (``---``), items are the blocks between
      them, which allows multi-line items (e.g. login + password + recovery info).
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    if _SEPARATOR_RE.search(text):
        return [block.strip() for block in _SEPARATOR_RE.split(text) if block.strip()]
    return [line.strip() for line in text.split("\n") if line.strip()]


def serialize_items(items: list[str]) -> str:
    """Inverse of :func:`parse_stock_payload` (used for exports / delivery files)."""
    if any("\n" in item for item in items):
        return "\n---\n".join(items) + "\n"
    return "\n".join(items) + "\n"


@dataclass
class AddStockResult:
    added: int
    duplicates: int
    available: int


@dataclass
class InventoryRow:
    product: Product
    category_name: str
    available: int | None
    sold: int


async def count_available(session: AsyncSession, product_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count()).where(StockItem.product_id == product_id, StockItem.is_sold.is_(False))
        )
        or 0
    )


async def add_stock(session: AsyncSession, product_id: int, items: list[str]) -> AddStockResult:
    """Add items, skipping duplicates of anything this product ever had (sold or not)."""
    product = await session.get(Product, product_id)
    if product is None:
        raise NotFound("Product not found.")
    if product.is_static:
        raise ShopError("This product delivers the same content to everyone, it has no stock.")

    existing = set((await session.scalars(select(StockItem.content).where(StockItem.product_id == product_id))).all())
    new_items: list[str] = []
    duplicates = 0
    for item in items:
        if item in existing:
            duplicates += 1
            continue
        existing.add(item)
        new_items.append(item)

    now = utcnow()
    session.add_all(StockItem(product_id=product_id, content=item, is_sold=False, created_at=now) for item in new_items)
    if new_items:
        product.low_stock_alerted = False
    await session.commit()
    return AddStockResult(len(new_items), duplicates, await count_available(session, product_id))


async def export_unsold(session: AsyncSession, product_id: int) -> list[str]:
    stmt = (
        select(StockItem.content)
        .where(StockItem.product_id == product_id, StockItem.is_sold.is_(False))
        .order_by(StockItem.id)
    )
    return list((await session.scalars(stmt)).all())


async def clear_unsold(session: AsyncSession, product_id: int) -> int:
    result = await session.execute(
        delete(StockItem)
        .where(StockItem.product_id == product_id, StockItem.is_sold.is_(False))
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    return result.rowcount or 0


async def inventory_overview(session: AsyncSession) -> list[InventoryRow]:
    rows = (
        await session.execute(
            select(Product, Category.name)
            .join(Category, Category.id == Product.category_id)
            .order_by(Category.sort_order, Category.id, Product.sort_order, Product.id)
        )
    ).all()
    ids = [p.id for p, _ in rows]
    available = await available_counts(session, ids)
    sold = await sold_counts(session, ids)
    return [
        InventoryRow(p, cat_name, None if p.is_static else available.get(p.id, 0), sold.get(p.id, 0))
        for p, cat_name in rows
    ]


async def low_stock_check(session: AsyncSession, product_id: int | None, threshold: int) -> int | None:
    """Return the remaining stock if admins should be alerted now (once per low-stock episode)."""
    if product_id is None:
        return None
    product = await session.get(Product, product_id, populate_existing=True)
    if product is None or product.delivery_type != DeliveryType.STOCK or product.low_stock_alerted:
        return None
    remaining = await count_available(session, product_id)
    if remaining > threshold:
        return None
    product.low_stock_alerted = True
    await session.commit()
    return remaining
