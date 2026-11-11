from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func, select

from shopbot.db.models import BalanceTransaction, StockItem, User
from shopbot.services import catalog, deposits, inventory, orders, users
from shopbot.services.errors import InsufficientBalance, OutOfStock, PriceChanged, ProductUnavailable


async def test_purchase_delivers_items_and_charges(sessionmaker, make_user, make_product):
    await make_user(1, balance=1000)
    product = await make_product(price=300, stock=["A", "B", "C", "D", "E"])

    async with sessionmaker() as session:
        result = await orders.purchase(session, user_id=1, product_id=product.id, quantity=2, max_quantity=50)

    assert result.new_balance == 400
    assert result.order.items == ["A", "B"]
    assert result.order.total == 600
    async with sessionmaker() as session:
        user = await session.get(User, 1)
        assert (user.balance, user.total_spent) == (400, 600)
        assert await inventory.count_available(session, product.id) == 3
        ledger = (await session.scalars(select(BalanceTransaction).where(BalanceTransaction.kind == "purchase"))).all()
        assert [t.amount for t in ledger] == [-600]


async def test_insufficient_balance_changes_nothing(sessionmaker, make_user, make_product):
    await make_user(1, balance=500)
    product = await make_product(price=300, stock=["A", "B"])

    async with sessionmaker() as session:
        with pytest.raises(InsufficientBalance):
            await orders.purchase(session, user_id=1, product_id=product.id, quantity=2, max_quantity=50)

    async with sessionmaker() as session:
        assert (await session.get(User, 1)).balance == 500
        assert await inventory.count_available(session, product.id) == 2
        assert await orders.count_orders(session) == 0


async def test_out_of_stock(sessionmaker, make_user, make_product):
    await make_user(1, balance=10_000)
    product = await make_product(price=100, stock=["A"])
    async with sessionmaker() as session:
        with pytest.raises(OutOfStock):
            await orders.purchase(session, user_id=1, product_id=product.id, quantity=2, max_quantity=50)


async def test_price_change_and_hidden_product(sessionmaker, make_user, make_product):
    await make_user(1, balance=10_000)
    product = await make_product(price=100, stock=["A", "B"])
    async with sessionmaker() as session:
        with pytest.raises(PriceChanged):
            await orders.purchase(
                session, user_id=1, product_id=product.id, quantity=1, max_quantity=5, expected_unit_price=99
            )
        await catalog.update_product(session, product.id, is_active=False)
        with pytest.raises(ProductUnavailable):
            await orders.purchase(session, user_id=1, product_id=product.id, quantity=1, max_quantity=5)


async def test_concurrent_purchases_never_oversell(sessionmaker, make_user, make_product):
    product = await make_product(price=100, stock=["A", "B", "C"])
    for uid in range(1, 7):
        await make_user(uid, balance=1000)

    async def buy(uid: int):
        async with sessionmaker() as session:
            try:
                return await orders.purchase(session, user_id=uid, product_id=product.id, quantity=1, max_quantity=5)
            except OutOfStock:
                return None

    results = await asyncio.gather(*(buy(uid) for uid in range(1, 7)))
    delivered = [r.order.items[0] for r in results if r]
    assert sorted(delivered) == ["A", "B", "C"]
    async with sessionmaker() as session:
        assert await inventory.count_available(session, product.id) == 0
        sold = await session.scalar(select(func.count()).where(StockItem.is_sold.is_(True)))
        assert sold == 3


async def test_static_product_is_unlimited_single_quantity(sessionmaker, make_user, make_product):
    await make_user(1, balance=1000)
    product = await make_product(price=200, static_text="https://example.com/download")
    async with sessionmaker() as session:
        first = await orders.purchase(session, user_id=1, product_id=product.id, quantity=1, max_quantity=50)
        second = await orders.purchase(session, user_id=1, product_id=product.id, quantity=1, max_quantity=50)
    assert first.order.items == ["https://example.com/download"]
    assert second.new_balance == 600


async def test_add_stock_skips_duplicates_including_sold(sessionmaker, make_user, make_product):
    await make_user(1, balance=1000)
    product = await make_product(price=100, stock=["A", "B"])
    async with sessionmaker() as session:
        await orders.purchase(session, user_id=1, product_id=product.id, quantity=1, max_quantity=5)
        result = await inventory.add_stock(session, product.id, ["A", "B", "C", "C"])
    assert (result.added, result.duplicates, result.available) == (1, 3, 2)


async def test_low_stock_alert_fires_once(sessionmaker, make_product):
    product = await make_product(price=100, stock=["A", "B"])
    async with sessionmaker() as session:
        assert await inventory.low_stock_check(session, product.id, threshold=5) == 2
        assert await inventory.low_stock_check(session, product.id, threshold=5) is None
        await inventory.add_stock(session, product.id, ["C"])  # restock re-arms the alert
        assert await inventory.low_stock_check(session, product.id, threshold=5) == 3


async def test_credit_deposit_is_idempotent(sessionmaker, make_user):
    await make_user(1)
    async with sessionmaker() as session:
        deposit = await deposits.create_deposit(session, user_id=1, amount=2500, provider="test")

    async def credit():
        async with sessionmaker() as session:
            return await deposits.credit_deposit(session, deposit.id, paid_asset="USDT", paid_amount="25")

    results = await asyncio.gather(credit(), credit(), credit())
    assert sum(r is not None for r in results) == 1
    async with sessionmaker() as session:
        user = await session.get(User, 1)
        assert (user.balance, user.total_deposited) == (2500, 2500)


async def test_admin_adjust_cannot_go_negative(sessionmaker, make_user):
    await make_user(1, balance=100)
    async with sessionmaker() as session:
        with pytest.raises(InsufficientBalance):
            await users.admin_adjust_balance(session, 1, -200, admin_id=99)
        assert await users.admin_adjust_balance(session, 1, -100, admin_id=99) == 0


async def test_delete_category_keeps_order_history(sessionmaker, make_user, make_product):
    await make_user(1, balance=1000)
    product = await make_product(price=100, stock=["A"])
    async with sessionmaker() as session:
        result = await orders.purchase(session, user_id=1, product_id=product.id, quantity=1, max_quantity=5)
        assert await catalog.delete_category(session, product.category_id)
    async with sessionmaker() as session:
        order = await orders.get_user_order(session, 1, result.order.id)
        assert order is not None and order.product_id is None and order.items == ["A"]
