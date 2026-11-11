# Database Schema

## Current Sprint 1-3 schema

Models are defined in `commerce_api/db/models.py` and the schema is changed through Alembic, not startup `create_all`. All IDs are UUIDs and timestamps are timezone-aware UTC. The existing Telegram bot has a separate legacy schema in `shopbot/db/models.py`; it is not part of the commerce database.

| Table | Purpose and important fields |
| --- | --- |
| `users` | Global login identity, unique normalized email, full name, Argon2id password hash, platform-admin flag, created timestamp. No merchant data is stored here. |
| `tenants` | Merchant account (`name`, unique slug, created timestamp). Tenant rows are protected by forced RLS. |
| `tenant_memberships` | User-to-tenant membership and `owner`/`admin`/`staff` role. Unique per tenant/user, FK-cascaded, role check constraint, tenant RLS. |
| `refresh_sessions` | SHA-256 hash of a random refresh token, user FK, expiry, revocation and creation timestamps. Raw refresh tokens are returned only once and never stored. |
| `categories` | Tenant-owned categories with tenant-unique slugs and RLS. |
| `products` | Tenant-owned product descriptions, category, active/draft state, price in minor currency units, and currency. Category relation is tenant-composite. |
| `product_variants` | Tenant-owned SKU and optional price override; composite FK ties it to a product in the same tenant. |
| `warehouses` | Tenant-owned warehouse with tenant-unique code. |
| `inventory_balances` | Per-tenant, variant, and warehouse on-hand/reserved/safety quantities using `NUMERIC(18,3)`. Constraints prevent negative quantities and reserved above on-hand. |
| `stock_reservations` | Tenant-scoped quantity holds, idempotency key, active/released/expired/deducted state, and expiry timestamp. |
| `stock_movements` | Tenant-scoped receipt/reservation/release/deduction/transfer/adjustment/return audit entries with positive decimal quantity and idempotency key. |
| `customers` | Tenant-owned buyer identity, optional normalized email/phone. |
| `customer_addresses` | Tenant/customer-scoped delivery contact and structured address snapshot source. |
| `carts`, `cart_items` | Active tenant/customer carts and variant quantities; checkout key is unique per tenant. |
| `orders`, `order_items` | Immutable catalog/price/address snapshots with separate payment and fulfillment states. |
| `payment_attempts` | Provider/reference/idempotency and expected amount/currency; `verified_at` records server verification. |
| `digital_assets` | Encrypted single-use deliverables, tenant/variant scoped and reserved to an order item before payment-gated release. |

No ledger, refund/settlement, dispatch, channel, AI, or subscription tables exist yet. Those schemas must be introduced in their owning sprint with migrations and tenant foreign keys from their first revision.

## Current relationships

- User has many tenant memberships and refresh sessions.
- Tenant has many memberships.
- Deleting a user or tenant cascades to memberships; deleting a user cascades to refresh sessions.
- Tenant owns categories, products, variants, warehouses, balances, reservations, and movements.
- Composite foreign keys include `tenant_id` between catalog and inventory records, preventing cross-tenant references at the database layer.
- A balance is unique per tenant/variant/warehouse. Reservation and movement idempotency keys are unique within a tenant.
- Checkout keys are unique per tenant; order lines snapshot product, variant, SKU, product type, quantity and unit price.
- Payment status and fulfillment status are separate; mixed carts also track fulfillment per line.
- Digital asset plaintext is never stored. Fernet ciphertext is stored in Postgres and requires a separate encryption key.

## Invariants and caveats

- Migrations are owned by `commerce_migrator`; the API connects as the non-owner `commerce_runtime` role.
- RLS is enabled and forced on every tenant-owned table. The API sets transaction-local tenant context only after authentication and membership checks.
- Current role values are constrained to owner, admin, and staff. Platform-admin status is global and is only changed by the explicit administrative CLI operation.
- Currency amounts are integer minor units; physical quantities use fixed-precision `NUMERIC(18,3)`.
- Reservations are reflected in `inventory_balances.reserved`; movement records are inserted in the same transaction as each stock change.
- Future merchant-owned tables must carry a non-null tenant FK, tenant-aware unique constraints and indexes, and RLS policies in the same migration that creates the table.
- Future money uses integer minor units; fractional quantities use `NUMERIC`, not binary floating point. Ledger and order snapshot policies are specified in their domain documents.