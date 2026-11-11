from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_api.dependencies import TenantAdmin, get_db
from commerce_api.schemas import (
    AddressCreateRequest,
    AddressResponse,
    CartCreateRequest,
    CartItemCreateRequest,
    CartItemResponse,
    CartResponse,
    CheckoutRequest,
    CustomerCreateRequest,
    CustomerResponse,
    OrderItemResponse,
    OrderResponse,
)
from commerce_api.services import carts, customers
from commerce_api.services.orders import checkout_cart, get_order, list_customer_orders

router = APIRouter(tags=["commerce"])


def _order_response(order, items) -> OrderResponse:
    return OrderResponse(
        id=order.id,
        tenant_id=order.tenant_id,
        customer_id=order.customer_id,
        checkout_key=order.checkout_key,
        source=order.source,
        currency=order.currency,
        subtotal_minor=order.subtotal_minor,
        total_minor=order.total_minor,
        payment_status=order.payment_status,
        fulfillment_status=order.fulfillment_status,
        shipping_address_snapshot=order.shipping_address_snapshot,
        items=[OrderItemResponse.model_validate(item) for item in items],
        created_at=order.created_at,
    )


async def _cart_response(session: AsyncSession, tenant_id: UUID, cart) -> CartResponse:
    items = await carts.list_cart_items(session, tenant_id=tenant_id, cart_id=cart.id)
    return CartResponse(
        id=cart.id,
        tenant_id=cart.tenant_id,
        customer_id=cart.customer_id,
        status=cart.status,
        items=[CartItemResponse.model_validate(item) for item in items],
        created_at=cart.created_at,
        updated_at=cart.updated_at,
    )


@router.post("/customers", response_model=CustomerResponse, status_code=201)
async def create_customer(
    values: CustomerCreateRequest,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await customers.create_customer(session, access.tenant_id, values)


@router.get("/customers", response_model=list[CustomerResponse])
async def list_customers(
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    return await customers.list_customers(session, access.tenant_id, offset=offset, limit=limit)


@router.post("/customers/{customer_id}/addresses", response_model=AddressResponse, status_code=201)
async def create_address(
    customer_id: UUID,
    values: AddressCreateRequest,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await customers.create_address(
        session, tenant_id=access.tenant_id, customer_id=customer_id, values=values
    )


@router.get("/customers/{customer_id}/addresses", response_model=list[AddressResponse])
async def list_addresses(
    customer_id: UUID,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await customers.list_addresses(session, tenant_id=access.tenant_id, customer_id=customer_id)


@router.post("/carts", response_model=CartResponse, status_code=201)
async def create_cart(
    values: CartCreateRequest,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    cart = await carts.create_cart(session, tenant_id=access.tenant_id, customer_id=values.customer_id)
    return await _cart_response(session, access.tenant_id, cart)


@router.get("/carts/{cart_id}", response_model=CartResponse)
async def get_cart(
    cart_id: UUID,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    cart = await carts.get_cart(session, tenant_id=access.tenant_id, cart_id=cart_id)
    return await _cart_response(session, access.tenant_id, cart)


@router.post("/carts/{cart_id}/items", response_model=CartItemResponse, status_code=201)
async def add_cart_item(
    cart_id: UUID,
    values: CartItemCreateRequest,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await carts.add_item(
        session,
        tenant_id=access.tenant_id,
        cart_id=cart_id,
        variant_id=values.variant_id,
        quantity=values.quantity,
    )


@router.post("/carts/{cart_id}/checkout", response_model=OrderResponse, status_code=201)
async def checkout(
    cart_id: UUID,
    values: CheckoutRequest,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    order = await checkout_cart(
        session,
        tenant_id=access.tenant_id,
        cart_id=cart_id,
        actor_user_id=access.user.id,
        values=values,
    )
    fresh_order, items = await get_order(session, tenant_id=access.tenant_id, order_id=order.id)
    return _order_response(fresh_order, items)


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def read_order(
    order_id: UUID,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    order, items = await get_order(session, tenant_id=access.tenant_id, order_id=order_id)
    return _order_response(order, items)


@router.get("/customers/{customer_id}/orders", response_model=list[OrderResponse])
async def read_customer_orders(
    customer_id: UUID,
    access: TenantAdmin,
    session: Annotated[AsyncSession, Depends(get_db)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    orders = await list_customer_orders(
        session, tenant_id=access.tenant_id, customer_id=customer_id, offset=offset, limit=limit
    )
    results = []
    for order in orders:
        _, items = await get_order(session, tenant_id=access.tenant_id, order_id=order.id)
        results.append(_order_response(order, items))
    return results
