from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_api.dependencies import get_db
from commerce_api.schemas import OnboardingRequest, OnboardingResponse, TenantResponse, UserResponse
from commerce_api.services.tenants import onboard_merchant

router = APIRouter(prefix="/onboarding", tags=["merchant onboarding"])


@router.post("", response_model=OnboardingResponse, status_code=status.HTTP_201_CREATED)
async def create_merchant_account(
    values: OnboardingRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> OnboardingResponse:
    user, tenant, tokens = await onboard_merchant(session, values, request.app.state.settings)
    return OnboardingResponse(
        user=UserResponse(id=user.id, email=user.email, full_name=user.full_name),
        tenant=TenantResponse.model_validate(tenant),
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )