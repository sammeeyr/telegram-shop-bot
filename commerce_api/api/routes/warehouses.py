from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_api.dependencies import TenantAdmin, get_db
from commerce_api.schemas import WarehouseCreate, WarehouseResponse
from commerce_api.services import catalog

router = APIRouter(prefix="/warehouses", tags=["warehouses"])


@router.post("", response_model=WarehouseResponse, status_code=201)
async def create_warehouse(
    values: WarehouseCreate,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await catalog.create_warehouse(session, access.tenant_id, values)


@router.get("", response_model=list[WarehouseResponse])
async def list_warehouses(
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await catalog.list_warehouses(session, access.tenant_id)