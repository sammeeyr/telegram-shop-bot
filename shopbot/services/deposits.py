"""Balance top-ups (deposits) persistence and idempotent crediting."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shopbot.db.models import Deposit, DepositStatus, utcnow
from shopbot.services.locks import money_lock
from shopbot.services.users import change_balance


@dataclass
class CreditResult:
    deposit: Deposit
    new_balance: int


async def create_deposit(session: AsyncSession, *, user_id: int, amount: int, provider: str) -> Deposit:
    deposit = Deposit(user_id=user_id, amount=amount, provider=provider, status=DepositStatus.PENDING, created_at=utcnow())
    session.add(deposit)
    await session.commit()
    return deposit


async def attach_invoice(
    session: AsyncSession, deposit_id: int, *, external_id: str, pay_url: str | None, expires_at: datetime | None
) -> Deposit:
    deposit = await session.get(Deposit, deposit_id)
    assert deposit is not None
    deposit.external_id = external_id
    deposit.pay_url = pay_url
    deposit.expires_at = expires_at
    await session.commit()
    return deposit


async def get_deposit(session: AsyncSession, deposit_id: int) -> Deposit | None:
    return await session.get(Deposit, deposit_id, populate_existing=True)


async def set_status_if_pending(session: AsyncSession, deposit_id: int, status: DepositStatus) -> bool:
    result = await session.execute(
        update(Deposit)
        .where(Deposit.id == deposit_id, Deposit.status == DepositStatus.PENDING)
        .values(status=status)
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    return result.rowcount == 1


async def credit_deposit(
    session: AsyncSession, deposit_id: int, *, paid_asset: str | None = None, paid_amount: str | None = None
) -> CreditResult | None:
    """Mark a pending deposit as paid and credit the user's balance.

    Idempotent: only the call that flips ``pending -> paid`` credits the balance;
    every other call returns ``None``.
    """
    async with money_lock():
        try:
            flipped = await session.execute(
                update(Deposit)
                .where(Deposit.id == deposit_id, Deposit.status == DepositStatus.PENDING)
                .values(status=DepositStatus.PAID, paid_at=utcnow(), paid_asset=paid_asset, paid_amount=paid_amount)
                .execution_options(synchronize_session=False)
            )
            if flipped.rowcount != 1:
                await session.rollback()
                return None
            deposit = await session.get(Deposit, deposit_id, populate_existing=True)
            assert deposit is not None
            new_balance = await change_balance(
                session, deposit.user_id, deposit.amount, kind="deposit",
                reference=f"deposit:{deposit.id}", count_as_deposit=True,
            )
            await session.commit()
            return CreditResult(deposit=deposit, new_balance=new_balance)
        except Exception:
            await session.rollback()
            raise


async def list_pending(session: AsyncSession, *, provider: str, limit: int = 1000) -> list[Deposit]:
    stmt = (
        select(Deposit)
        .where(Deposit.provider == provider, Deposit.status == DepositStatus.PENDING)
        .order_by(Deposit.id)
        .limit(limit)
    )
    return list((await session.scalars(stmt)).all())


async def count_pending_for_user(session: AsyncSession, user_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count(Deposit.id)).where(Deposit.user_id == user_id, Deposit.status == DepositStatus.PENDING)
        )
        or 0
    )


async def count_user_deposits(session: AsyncSession, user_id: int) -> int:
    return int(await session.scalar(select(func.count(Deposit.id)).where(Deposit.user_id == user_id)) or 0)


async def list_user_deposits(session: AsyncSession, user_id: int, *, offset: int, limit: int) -> list[Deposit]:
    stmt = select(Deposit).where(Deposit.user_id == user_id).order_by(Deposit.id.desc()).offset(offset).limit(limit)
    return list((await session.scalars(stmt)).all())
