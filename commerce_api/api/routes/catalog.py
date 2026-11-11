from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_api.dependencies import TenantAdmin, get_db
from commerce_api.schemas import (
    CategoryCreate,
    CategoryResponse,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    DigitalAssetCreateRequest,
    DigitalAssetResponse,
    VariantCreate,
    VariantResponse,
)
from commerce_api.services import catalog
from commerce_api.services.digital_delivery import add_digital_asset

router = APIRouter(tags=["catalog"])


@router.post("/categories", response_model=CategoryResponse, status_code=201)
async def create_category(
    values: CategoryCreate,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await catalog.create_category(session, access.tenant_id, values)


@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await catalog.list_categories(session, access.tenant_id)


@router.post("/products", response_model=ProductResponse, status_code=201)
async def create_product(
    values: ProductCreate,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await catalog.create_product(session, access.tenant_id, values)


@router.get("/products", response_model=list[ProductResponse])
async def list_products(
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    return await catalog.list_products(session, access.tenant_id, offset=offset, limit=limit)


@router.patch("/products/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: UUID,
    values: ProductUpdate,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await catalog.update_product(session, access.tenant_id, product_id, values)


@router.post("/products/{product_id}/variants", response_model=VariantResponse, status_code=201)
async def create_variant(
    product_id: UUID,
    values: VariantCreate,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await catalog.create_variant(session, access.tenant_id, product_id, values)


@router.post("/variants/{variant_id}/digital-assets", response_model=DigitalAssetResponse, status_code=201)
async def provision_digital_asset(
    variant_id: UUID,
    values: DigitalAssetCreateRequest,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
):
    asset = await add_digital_asset(
        session,
        tenant_id=access.tenant_id,
        variant_id=variant_id,
        plaintext=values.asset.get_secret_value(),
        idempotency_key=values.idempotency_key,
        settings=request.app.state.settings,
    )
    return DigitalAssetResponse(id=asset.id, variant_id=asset.variant_id, status=asset.status)