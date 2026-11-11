from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shopbot.db.models import BalanceTransaction, User, utcnow
from shopbot.services.errors import InsufficientBalance, NotFound

# Don't write last_seen_at on every single update.
LAST_SEEN_RESOLUTION = timedelta(minutes=5)


async def get_or_create_user(
    session: AsyncSession, user_id: int, username: str | None, full_name: str
) -> tuple[User, bool]:
    now = utcnow()
    user = await session.get(User, user_id)
    if user is None:
        user = User(
            id=user_id, username=username, full_name=full_name, balance=0, total_deposited=0,
            total_spent=0, is_banned=False, created_at=now, last_seen_at=now,
        )
        session.add(user)
        try:
            await session.commit()
            return user, True
        except IntegrityError:  # created concurrently by another update
            await session.rollback()
            user = await session.get(User, user_id)
            if user is None:
                raise
            return user, False

    if user.username != username or user.full_name != full_name or now - user.last_seen_at > LAST_SEEN_RESOLUTION:
        user.username = username
        user.full_name = full_name
        user.last_seen_at = now
        await session.commit()
    return user, False


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def find_user(session: AsyncSession, query: str) -> User | None:
    """Find by numeric Telegram id or @username."""
    q = query.strip().removeprefix("@").strip()
    if not q:
        return None
    if q.isdigit():
        return await session.get(User, int(q))
    return await session.scalar(select(User).where(func.lower(User.username) == q.lower()))


async def change_balance(
    session: AsyncSession,
    user_id: int,
    delta: int,
    *,
    kind: str,
    reference: str = "",
    note: str = "",
    count_as_deposit: bool = False,
    count_as_spent: bool = False,
) -> int:
    """Atomically apply a balance change and write a ledger entry.

    Runs inside the caller's transaction (the caller commits). A negative delta
    only succeeds if the balance covers it. Returns the new balance.
    """
    values: dict = {"balance": User.balance + delta}
    if count_as_deposit:
        values["total_deposited"] = User.total_deposited + delta
    if count_as_spent:
        values["total_spent"] = User.total_spent - delta

    stmt = update(User).where(User.id == user_id)
    if delta < 0:
        stmt = stmt.where(User.balance >= -delta)
    result = await session.execute(stmt.values(**values).execution_options(synchronize_session=False))

    if result.rowcount != 1:
        current = await session.scalar(select(User.balance).where(User.id == user_id))
        if current is None:
            raise NotFound("User not found.")
        raise InsufficientBalance(required=-delta, balance=current)

    user = await session.get(User, user_id, populate_existing=True)
    assert user is not None
    session.add(
        BalanceTransaction(
            user_id=user_id, amount=delta, kind=kind, balance_after=user.balance,
            reference=reference, note=note[:256], created_at=utcnow(),
        )
    )
    return user.balance


async def admin_adjust_balance(session: AsyncSession, user_id: int, delta: int, *, admin_id: int) -> int:
    try:
        new_balance = await change_balance(
            session, user_id, delta, kind="admin", reference=f"admin:{admin_id}", note="Manual adjustment"
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return new_balance


async def set_banned(session: AsyncSession, user_id: int, banned: bool) -> User | None:
    user = await session.get(User, user_id)
    if user is None:
        return None
    user.is_banned = banned
    await session.commit()
    return user


async def active_user_ids(session: AsyncSession) -> list[int]:
    return list((await session.scalars(select(User.id).where(User.is_banned.is_(False)).order_by(User.id))).all())
