from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_api.core.config import Settings
from commerce_api.core.security import create_access_token, hash_refresh_token, new_refresh_token
from commerce_api.db.models import RefreshSession, User
from commerce_api.schemas import TokenResponse


async def issue_tokens(session: AsyncSession, user: User, settings: Settings) -> TokenResponse:
    access_token, expires_in = create_access_token(user.id, settings)
    refresh_token = new_refresh_token()
    session.add(
        RefreshSession(
            token_hash=hash_refresh_token(refresh_token),
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
        )
    )
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, expires_in=expires_in)


async def rotate_refresh_token(
    session: AsyncSession, raw_token: str, settings: Settings
) -> tuple[User, TokenResponse] | None:
    now = datetime.now(UTC)
    result = await session.execute(
        update(RefreshSession)
        .where(
            RefreshSession.token_hash == hash_refresh_token(raw_token),
            RefreshSession.revoked_at.is_(None),
            RefreshSession.expires_at > now,
        )
        .values(revoked_at=now)
        .returning(RefreshSession.user_id)
    )
    user_id: UUID | None = result.scalar_one_or_none()
    if user_id is None:
        return None
    user = await session.get(User, user_id)
    if user is None:
        return None
    return user, await issue_tokens(session, user, settings)