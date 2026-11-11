# Domain Module Boundaries

## Architecture rule

Build a modular monolith first. Domain modules own business rules and persistence; channel/API/UI adapters depend on domain services, never the reverse. Share one catalog, price, checkout, order, inventory, payment, and fulfillment implementation across all channels. Do not copy commerce rules into bots, webhooks, storefront pages, or AI prompts.

## Planned modules and ownership

| Module | Owns | Must not own |
| --- | --- | --- |
| Identity and tenancy | Users, tenants, memberships, RBAC, tenant context, platform administration | Catalog or order business rules |
| Catalog | Categories, products, variants, attributes, publication and price snapshots | Channel-specific rendering |
| Inventory | Warehouses, locations, stock movements, reservations, safety stock, transfers, adjustments | Payment state or channel callbacks |
| Customers and checkout | Customer profiles/addresses, carts, discounts, delivery quotes, checkout validation | Provider settlement confirmation |
| Orders | Source, immutable order/item/address snapshots, separate payment and fulfillment state machines, timelines | External provider SDKs |
| Payments and ledger | Provider-neutral payments, webhook events, reconciliation, refunds, settlements, balanced double-entry ledger | Frontend redirects as proof of payment |
| Dispatch | Delivery zones/rates, riders, assignments, shipments, tracking, attempts, proof and COD reconciliation | Catalog/inventory policy |
| Channels | Telegram, web storefront/sales pages, WhatsApp, admin/API adapters and connections | Duplicated domain decisions |
| Notifications and outbox | Durable domain-event delivery, retries, dedupe, dead-letter visibility | Authoritative order/payment state |
| Analytics | Tenant-scoped projections and reports | Mutating transactional records |
| AI and approvals | Agent definitions, allowlisted service tools, approval queue, usage/audit records | Direct DB access or privileged mutation |
| Subscriptions and developer access | Platform plans, API credentials, quotas, usage metering and billing entitlement | Bypass of tenant authorization |

## Current code map

Sprints 1-3 implement `commerce_api.core` (settings/security), `commerce_api.db` (models/session/RLS), `commerce_api.services` (identity, tenant, catalog, inventory, customer, cart, order, and digital-delivery services), `commerce_api.api.routes` (FastAPI adapters), and `commerce_api.migrations`. Payment providers/settlement, storefronts, channels, dispatch, and AI remain future work. Existing `shopbot` remains an independent legacy channel application.

## Service contract expectations

Every command receives an authenticated actor and explicit tenant context, validates resource ownership, and commits its business transaction atomically. Services return typed results and domain errors. External calls are outside the transaction and coordinated through idempotency plus an outbox once asynchronous processing is introduced. Test domain services without FastAPI or channel SDKs.