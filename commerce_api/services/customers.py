from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_api.db.models import Customer, CustomerAddress
from commerce_api.schemas import AddressCreateRequest, CustomerCreateRequest
from commerce_api.services.errors import ResourceNotFound


async def create_customer(
    session: AsyncSession, tenant_id: UUID, values: CustomerCreateRequest
) -> Customer:
    customer = Customer(
        tenant_id=tenant_id,
        full_name=values.full_name,
        email=str(values.email).lower() if values.email else None,
        phone=values.phone,
    )
    session.add(customer)
    await session.flush()
    return customer


async def list_customers(
    session: AsyncSession, tenant_id: UUID, *, offset: int, limit: int
) -> list[Customer]:
    rows = await session.scalars(
        select(Customer)
        .where(Customer.tenant_id == tenant_id)
        .order_by(Customer.created_at.desc(), Customer.id)
        .offset(offset)
        .limit(limit)
    )
    return list(rows.all())


async def create_address(
    session: AsyncSession, *, tenant_id: UUID, customer_id: UUID, values: AddressCreateRequest
) -> CustomerAddress:
    customer = await session.scalar(
        select(Customer).where(Customer.tenant_id == tenant_id, Customer.id == customer_id)
    )
    if customer is None:
        raise ResourceNotFound("Customer not found")
    if values.is_default:
        await session.execute(
            update(CustomerAddress)
            .where(CustomerAddress.tenant_id == tenant_id, CustomerAddress.customer_id == customer_id)
            .values(is_default=False)
        )
    address = CustomerAddress(
        tenant_id=tenant_id,
        customer_id=customer_id,
        label=values.label.strip(),
        recipient_name=values.recipient_name,
        phone=values.phone,
        address=values.address,
        is_default=values.is_default,
    )
    session.add(address)
    await session.flush()
    return address


async def list_addresses(
    session: AsyncSession, *, tenant_id: UUID, customer_id: UUID
) -> list[CustomerAddress]:
    customer_exists = await session.scalar(
        select(Customer.id).where(Customer.tenant_id == tenant_id, Customer.id == customer_id)
    )
    if customer_exists is None:
        raise ResourceNotFound("Customer not found")
    rows = await session.scalars(
        select(CustomerAddress)
        .where(CustomerAddress.tenant_id == tenant_id, CustomerAddress.customer_id == customer_id)
        .order_by(CustomerAddress.is_default.desc(), CustomerAddress.created_at.desc())
    )
    return list(rows.all())