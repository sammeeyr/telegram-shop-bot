from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_api.db.models import Category, Product, ProductVariant, Warehouse
from commerce_api.schemas import CategoryCreate, ProductCreate, ProductUpdate, VariantCreate, WarehouseCreate
from commerce_api.services.errors import ResourceNotFound


async def create_category(session: AsyncSession, tenant_id, values: CategoryCreate) -> Category:
    category = Category(tenant_id=tenant_id, name=values.name, slug=values.slug)
    session.add(category)
    await session.flush()
    return category


async def list_categories(session: AsyncSession, tenant_id) -> list[Category]:
    rows = await session.scalars(
        select(Category).where(Category.tenant_id == tenant_id).order_by(Category.name, Category.id)
    )
    return list(rows.all())


async def create_product(session: AsyncSession, tenant_id, values: ProductCreate) -> Product:
    if values.category_id is not None:
        category = await session.scalar(
            select(Category).where(Category.tenant_id == tenant_id, Category.id == values.category_id)
        )
        if category is None:
            raise ResourceNotFound("Category not found")
    product = Product(
        tenant_id=tenant_id,
        category_id=values.category_id,
        name=values.name,
        slug=values.slug,
        description=values.description,
        unit_price_minor=values.unit_price_minor,
        currency=values.currency,
        product_type=values.product_type,
        is_active=values.is_active,
    )
    session.add(product)
    await session.flush()
    return product


async def list_products(
    session: AsyncSession, tenant_id, *, offset: int, limit: int
) -> list[Product]:
    rows = await session.scalars(
        select(Product)
        .where(Product.tenant_id == tenant_id)
        .order_by(Product.created_at.desc(), Product.id)
        .offset(offset)
        .limit(limit)
    )
    return list(rows.all())


async def create_variant(
    session: AsyncSession, tenant_id, product_id, values: VariantCreate
) -> ProductVariant:
    product = await session.scalar(
        select(Product).where(Product.tenant_id == tenant_id, Product.id == product_id)
    )
    if product is None:
        raise ResourceNotFound("Product not found")
    variant = ProductVariant(
        tenant_id=tenant_id,
        product_id=product.id,
        name=values.name,
        sku=values.sku,
        price_minor=values.price_minor,
        is_active=values.is_active,
    )
    session.add(variant)
    await session.flush()
    return variant


async def create_warehouse(session: AsyncSession, tenant_id, values: WarehouseCreate) -> Warehouse:
    warehouse = Warehouse(tenant_id=tenant_id, name=values.name, code=values.code)
    session.add(warehouse)
    await session.flush()
    return warehouse


async def list_warehouses(session: AsyncSession, tenant_id) -> list[Warehouse]:
    rows = await session.scalars(
        select(Warehouse).where(Warehouse.tenant_id == tenant_id).order_by(Warehouse.name, Warehouse.id)
    )
    return list(rows.all())


async def update_product(
    session: AsyncSession, tenant_id, product_id, values: ProductUpdate
) -> Product:
    product = await session.scalar(
        select(Product).where(Product.tenant_id == tenant_id, Product.id == product_id)
    )
    if product is None:
        raise ResourceNotFound("Product not found")
    changes = values.model_dump(exclude_unset=True)
    if "category_id" in changes and changes["category_id"] is not None:
        category = await session.scalar(
            select(Category).where(Category.tenant_id == tenant_id, Category.id == changes["category_id"])
        )
        if category is None:
            raise ResourceNotFound("Category not found")
    for field, value in changes.items():
        setattr(product, field, value)
    await session.flush()
    return product