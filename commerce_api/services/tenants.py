from __future__ import annotations

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from commerce_api.core.config import Settings
from commerce_api.core.security import hash_password
from commerce_api.db.models import MembershipRole, Tenant, TenantMembership, User
from commerce_api.db.rls import set_rls_context
from commerce_api.schemas import OnboardingRequest, TenantCreateRequest, TokenResponse
from commerce_api.services.auth import issue_tokens


async def provision_tenant(session: AsyncSession, user: User, values: TenantCreateRequest) -> Tenant:
    tenant = Tenant(id=uuid4(), name=values.name, slug=values.slug)
    await set_rls_context(
        session, user_id=str(user.id), tenant_id=str(tenant.id), is_platform_admin=user.is_platform_admin
    )
    session.add(tenant)
    session.add(TenantMembership(tenant_id=tenant.id, user_id=user.id, role=MembershipRole.OWNER.value))
    await session.flush()
    return tenant


async def onboard_merchant(
    session: AsyncSession, values: OnboardingRequest, settings: Settings
) -> tuple[User, Tenant, TokenResponse]:
    user = User(
        email=str(values.email).lower(),
        full_name=values.full_name,
        password_hash=hash_password(values.password.get_secret_value()),
    )
    session.add(user)
    await session.flush()
    tenant = await provision_tenant(
        session,
        user,
        TenantCreateRequest(name=values.tenant_name, slug=values.tenant_slug),
    )
    tokens = await issue_tokens(session, user, settings)
    return user, tenant, tokens