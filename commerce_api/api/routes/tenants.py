from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_api.db.models import MembershipRole, Tenant, TenantMembership, User
from commerce_api.dependencies import CurrentUser, TenantAdmin, TenantMember, get_db
from commerce_api.schemas import (
    MembershipCreateRequest,
    MembershipResponse,
    MembershipUpdateRequest,
    TenantCreateRequest,
    TenantResponse,
    TenantUpdateRequest,
)
from commerce_api.services.tenants import provision_tenant

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("", response_model=TenantResponse, status_code=201)
async def create_tenant(
    values: TenantCreateRequest,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Tenant:
    return await provision_tenant(session, user, values)


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: UUID,
    access: TenantMember,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Tenant:
    if tenant_id != access.tenant_id:
        raise HTTPException(404, "Tenant not found")
    tenant = await session.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if tenant is None:
        raise HTTPException(404, "Tenant not found")
    return tenant


@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: UUID,
    values: TenantUpdateRequest,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Tenant:
    if tenant_id != access.tenant_id:
        raise HTTPException(404, "Tenant not found")
    tenant = await session.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if tenant is None:
        raise HTTPException(404, "Tenant not found")
    tenant.name = values.name
    await session.flush()
    return tenant


def _check_tenant_path(tenant_id: UUID, access) -> None:
    if tenant_id != access.tenant_id:
        raise HTTPException(404, "Tenant not found")


@router.get("/{tenant_id}/members", response_model=list[MembershipResponse])
async def list_members(
    tenant_id: UUID,
    access: TenantMember,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[MembershipResponse]:
    _check_tenant_path(tenant_id, access)
    rows = await session.execute(
        select(User.id, User.email, User.full_name, TenantMembership.role)
        .join(TenantMembership, TenantMembership.user_id == User.id)
        .where(TenantMembership.tenant_id == tenant_id)
        .order_by(User.email)
    )
    return [MembershipResponse(user_id=row.id, email=row.email, full_name=row.full_name, role=row.role) for row in rows]


@router.post("/{tenant_id}/members", response_model=MembershipResponse, status_code=201)
async def add_member(
    tenant_id: UUID,
    values: MembershipCreateRequest,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MembershipResponse:
    _check_tenant_path(tenant_id, access)
    if values.role == MembershipRole.ADMIN and access.role not in {MembershipRole.OWNER, "platform_admin"}:
        raise HTTPException(403, "Only an owner can grant the admin role")
    user = await session.scalar(select(User).where(User.email == str(values.email).lower()))
    if user is None:
        raise HTTPException(404, "User must register before joining a tenant")
    membership = TenantMembership(tenant_id=tenant_id, user_id=user.id, role=values.role)
    session.add(membership)
    await session.flush()
    return MembershipResponse(user_id=user.id, email=user.email, full_name=user.full_name, role=membership.role)


@router.patch("/{tenant_id}/members/{user_id}", response_model=MembershipResponse)
async def update_member_role(
    tenant_id: UUID,
    user_id: UUID,
    values: MembershipUpdateRequest,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MembershipResponse:
    _check_tenant_path(tenant_id, access)
    membership = await session.scalar(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user_id,
        )
    )
    if membership is None or membership.role == MembershipRole.OWNER:
        raise HTTPException(404, "Tenant member not found")
    if (
        access.role not in {MembershipRole.OWNER, "platform_admin"}
        and (membership.role == MembershipRole.ADMIN or values.role == MembershipRole.ADMIN)
    ):
        raise HTTPException(403, "Only an owner can change admin roles")
    membership.role = values.role
    user = await session.get(User, user_id)
    await session.flush()
    return MembershipResponse(user_id=user.id, email=user.email, full_name=user.full_name, role=membership.role)


@router.delete("/{tenant_id}/members/{user_id}", status_code=204)
async def remove_member(
    tenant_id: UUID,
    user_id: UUID,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    _check_tenant_path(tenant_id, access)
    membership = await session.scalar(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user_id,
        )
    )
    if membership is None or membership.role == MembershipRole.OWNER:
        raise HTTPException(404, "Tenant member not found")
    if access.role not in {MembershipRole.OWNER, "platform_admin"} and membership.role != MembershipRole.STAFF:
        raise HTTPException(403, "Only an owner can remove admins")
    await session.delete(membership)