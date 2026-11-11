from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_api.core.security import decode_access_token
from commerce_api.db.models import MembershipRole, TenantMembership, User
from commerce_api.db.rls import set_rls_context

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class TenantAccess:
    user: User
    tenant_id: UUID
    role: str


async def get_db(request: Request):
    factory = request.app.state.session_factory
    async with factory() as session:
        async with session.begin():
            yield session


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = decode_access_token(credentials.credentials, request.app.state.settings)
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid access token")
    return user


async def get_tenant_access(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    requested_tenant_id: Annotated[UUID, Header(alias="X-Tenant-ID")],
) -> TenantAccess:
    await set_rls_context(
        session,
        user_id=str(user.id),
        tenant_id=str(requested_tenant_id),
        is_platform_admin=user.is_platform_admin,
    )
    membership = await session.scalar(
        select(TenantMembership).where(
            TenantMembership.tenant_id == requested_tenant_id,
            TenantMembership.user_id == user.id,
        )
    )
    if membership is None and not user.is_platform_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant membership required")
    role = "platform_admin" if user.is_platform_admin else membership.role
    return TenantAccess(user=user, tenant_id=requested_tenant_id, role=role)


def require_roles(*allowed_roles: str):
    async def dependency(access: Annotated[TenantAccess, Depends(get_tenant_access)]) -> TenantAccess:
        if access.role != "platform_admin" and access.role not in allowed_roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient tenant role")
        return access

    return dependency


CurrentUser = Annotated[User, Depends(get_current_user)]
TenantMember = Annotated[TenantAccess, Depends(get_tenant_access)]
TenantAdmin = Annotated[TenantAccess, Depends(require_roles(MembershipRole.OWNER, MembershipRole.ADMIN))]