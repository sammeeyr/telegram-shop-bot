from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_api.core.security import hash_password, hash_refresh_token, verify_password
from commerce_api.db.models import RefreshSession, TenantMembership, User
from commerce_api.db.rls import set_rls_context
from commerce_api.dependencies import get_db
from commerce_api.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UserResponse
from commerce_api.services.auth import issue_tokens, rotate_refresh_token

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    values: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    user = User(
        email=str(values.email).lower(),
        full_name=values.full_name.strip(),
        password_hash=hash_password(values.password.get_secret_value()),
    )
    session.add(user)
    await session.flush()
    return UserResponse(id=user.id, email=user.email, full_name=user.full_name)


@router.post("/login", response_model=TokenResponse)
async def login(
    values: LoginRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    user = await session.scalar(select(User).where(User.email == str(values.email).lower()))
    if user is None or not verify_password(values.password.get_secret_value(), user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    await set_rls_context(
        session, user_id=str(user.id), tenant_id=str(values.tenant_id), is_platform_admin=user.is_platform_admin
    )
    if not user.is_platform_admin:
        membership = await session.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == values.tenant_id,
                TenantMembership.user_id == user.id,
            )
        )
        if membership is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant membership required")
    return await issue_tokens(session, user, request.app.state.settings)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    values: RefreshRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    result = await rotate_refresh_token(
        session, values.refresh_token.get_secret_value(), request.app.state.settings
    )
    if result is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")
    _, tokens = result
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    values: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await session.execute(
        update(RefreshSession)
        .where(
            RefreshSession.token_hash == hash_refresh_token(values.refresh_token.get_secret_value()),
            RefreshSession.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )