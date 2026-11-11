# API Specification

## Current API

The FastAPI application is served from `commerce_api.asgi:app`. Versioned routes are under `/api/v1`; interactive OpenAPI is available at `/docs` in a running development instance.

| Method | Path | Access | Behavior |
| --- | --- | --- | --- |
| `POST` | `/api/v1/auth/register` | Public | Create a global user account; Argon2id password hash. |
| `POST` | `/api/v1/onboarding` | Public | Atomically create merchant owner, tenant, owner membership, and tokens. |
| `POST` | `/api/v1/auth/login` | Public | Issue access/refresh tokens for an existing tenant member. |
| `POST` | `/api/v1/auth/refresh` | Public | Rotate a one-time refresh token. |
| `POST` | `/api/v1/auth/logout` | Public | Revoke the supplied refresh token. |
| `POST` | `/api/v1/tenants` | Authenticated | Create a tenant and make the caller its owner. |
| `GET` | `/api/v1/tenants/{tenant_id}` | Tenant member | Read the caller's tenant. |
| `PATCH` | `/api/v1/tenants/{tenant_id}` | Owner/admin | Update tenant name. |
| `GET` | `/api/v1/tenants/{tenant_id}/members` | Tenant member | List tenant memberships. |
| `POST` | `/api/v1/tenants/{tenant_id}/members` | Owner/admin | Add an existing user as staff; only owners grant admin. |
| `PATCH` | `/api/v1/tenants/{tenant_id}/members/{user_id}` | Owner/admin | Change a non-owner membership role. |
| `DELETE` | `/api/v1/tenants/{tenant_id}/members/{user_id}` | Owner/admin | Remove a non-owner membership. |
| `POST`, `GET` | `/api/v1/catalog/categories` | Tenant admin | Create/list categories. |
| `POST`, `GET` | `/api/v1/catalog/products` | Tenant admin | Create/list products with offset/limit. New products default to draft. |
| `PATCH` | `/api/v1/catalog/products/{product_id}` | Tenant admin | Edit product fields and publish/unpublish. |
| `POST` | `/api/v1/catalog/products/{product_id}/variants` | Tenant admin | Add an SKU variant. |
| `POST` | `/api/v1/catalog/variants/{variant_id}/digital-assets` | Tenant admin | Provision encrypted, single-use digital inventory; response contains no plaintext. |
| `POST`, `GET` | `/api/v1/warehouses` | Tenant admin | Create/list warehouses. |
| `PUT` | `/api/v1/inventory/balances` | Tenant admin | Configure safety stock for a variant/warehouse. |
| `POST` | `/api/v1/inventory/receipts` | Tenant admin | Receive stock with idempotency key. |
| `POST` | `/api/v1/inventory/adjustments`, `/returns`, `/transfers` | Tenant admin | Record signed count adjustments, returns, and atomic same-tenant warehouse transfers. |
| `GET` | `/api/v1/inventory/balances/{warehouse_id}/{variant_id}` | Tenant admin | Read on-hand, reserved, available, and safety quantities. |
| `GET` | `/api/v1/inventory/variants/{variant_id}/movements` | Tenant admin | Paginated stock movement history. |
| `POST` | `/api/v1/inventory/reservations` | Tenant admin | Atomically reserve available stock with an expiry and idempotency key. |
| `POST` | `/api/v1/inventory/reservations/{reservation_id}/release`, `/api/v1/inventory/reservations/{reservation_id}/deduct` | Tenant admin | Release or deduct a hold. |
| `POST` | `/api/v1/inventory/reservations/expire` | Tenant admin | Run a bounded expiry sweep. |
| `POST`, `GET` | `/api/v1/customers` | Tenant admin | Create/list tenant customers. |
| `POST`, `GET` | `/api/v1/customers/{customer_id}/addresses` | Tenant admin | Create/list customer addresses. |
| `POST`, `GET` | `/api/v1/carts` and `/api/v1/carts/{cart_id}` | Tenant admin | Create and retrieve carts. |
| `POST` | `/api/v1/carts/{cart_id}/items` | Tenant admin | Add a product variant to an active cart. |
| `POST` | `/api/v1/carts/{cart_id}/checkout` | Tenant admin | Create an idempotent order snapshot and pending payment attempt; reserve inventory. |
| `GET` | `/api/v1/orders/{order_id}` | Tenant admin | Read an order and immutable line snapshots. |
| `GET` | `/api/v1/customers/{customer_id}/orders` | Tenant admin | Paginated customer order history. |
| `GET` | `/health/live`, `/health/ready` | Public | Liveness and database readiness. |

Authenticated tenant requests require `Authorization: Bearer <access_token>` and `X-Tenant-ID: <uuid>`. Membership is reloaded and authorized on every request; tenant ID headers are selectors, never proof of access. Errors follow FastAPI validation responses; integrity conflicts return HTTP 409.

## Contract boundaries

Checkout and orders are implemented for the merchant API, including separate payment/fulfillment states and digital payment gates. No HTTP endpoint marks payments paid or releases digital plaintext. Payment providers/webhooks, customer-facing storefront access, channels, dispatch, analytics, and developer/MCP APIs remain unimplemented. Future endpoints must use tenant/resource authorization, idempotency, rate limits, and stable errors.

The existing Telegram bot continues to use its own internal handlers and is not yet a client of this API.