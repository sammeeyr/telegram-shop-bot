from __future__ import annotations

import pytest

from shopbot.db import create_engine, create_sessionmaker, init_db
from shopbot.db.models import DeliveryType
from shopbot.services import catalog, inventory, users


@pytest.fixture
async def sessionmaker(tmp_path):
    engine = create_engine(f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    await init_db(engine)
    yield create_sessionmaker(engine)
    await engine.dispose()


@pytest.fixture
def make_user(sessionmaker):
    async def _make(user_id: int = 1, balance: int = 0):
        async with sessionmaker() as session:
            user, _ = await users.get_or_create_user(session, user_id, f"user{user_id}", f"User {user_id}")
            if balance:
                await users.admin_adjust_balance(session, user_id, balance, admin_id=0)
            return user

    return _make


@pytest.fixture
def make_product(sessionmaker):
    async def _make(price: int = 500, stock: list[str] | None = None, static_text: str | None = None):
        async with sessionmaker() as session:
            category = await catalog.create_category(session, "Keys")
            product = await catalog.create_product(
                session,
                category_id=category.id,
                name="Game key",
                description="",
                price=price,
                delivery_type=DeliveryType.STATIC if static_text else DeliveryType.STOCK,
                static_text=static_text,
            )
            if stock:
                await inventory.add_stock(session, product.id, stock)
            return product

    return _make
