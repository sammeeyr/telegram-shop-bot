# Architecture

## Product direction

Cube Tech Commerce is a multi-tenant, channel-independent commerce and logistics platform. The commerce engine and domain services are the product foundation; Telegram, storefronts, sales pages, WhatsApp, admin tools, and developer integrations are adapters over shared services, not independent business systems.

The system starts as a modular monolith. Domain logic must not depend on FastAPI, aiogram, Next.js, WhatsApp, or a courier SDK. Adapters validate identity and channel input, establish a tenant context, call domain services, and format the result for that channel. Financial and inventory invariants belong in services and PostgreSQL transactions.

## Current implementation: Sprint 1

The `commerce_api` package currently provides a FastAPI application under `/api/v1`, PostgreSQL async sessions, Alembic migrations, merchant onboarding, Argon2id password hashing, short-lived JWT access tokens, hashed/rotating opaque refresh tokens, platform-admin promotion, tenant memberships with owner/admin/staff RBAC, and forced PostgreSQL RLS for tenant and membership rows. The API runtime uses a restricted database role distinct from the migration owner. `/health/live` and `/health/ready` provide process and database checks.

The existing `shopbot` remains a separate legacy digital-goods bot using its own SQLite database and Crypto Pay implementation. It is not yet a Cube Commerce channel adapter and does not share the new tenant database. Do not claim cross-channel checkout or shared inventory until later sprints migrate its behavior onto commerce services.

## Current implementation: Sprint 2

Tenant-scoped categories, products, variants/SKUs, warehouses, stock balances, stock movements, and reservations are implemented. Catalog/inventory services support publication, receiving, safety stock, conditional atomic reservation, expiry, release, deduction, adjustment, return, and paired warehouse transfer. All new tables have composite tenant references and forced RLS. Checkout and orders do not yet consume this inventory service.

## Current implementation: Sprint 3

Tenant-scoped customer/address, cart, checkout, order/item, payment-attempt, and digital-asset records are implemented. Checkout snapshots catalog and address data and reserves physical stock or encrypted digital assets. Payment and fulfillment states are independent. Only an internal verified-payment service can unlock digital delivery; provider adapters and public payment/webhook routes remain Sprint 4.

## Cloud provider guidance

Neon Postgres is compatible with the current SQLAlchemy/asyncpg/Alembic stack. Use a pooled connection for API traffic and a direct connection for migrations. Cloudflare Hyperdrive is only needed if the backend moves to Workers; the current FastAPI service can connect directly to PostgreSQL.

Keep uploads behind a private S3-compatible adapter. Neon Object Storage is useful when preview files must branch with the database; Cloudflare R2 fits naturally with Cloudflare CDN/edge delivery. Store object keys in Postgres, not file bodies. Keep license keys and other secrets in encrypted digital-asset records, not public buckets. Turnstile is optional for browser-facing public forms and must be verified server-side; it does not authenticate users or verify payments. D1 is not a drop-in replacement for the PostgreSQL system of record because this platform relies on PostgreSQL RLS, composite foreign keys, and transactional locking.

## Target module boundaries

See [DOMAIN_MODULES.md](DOMAIN_MODULES.md). Core modules are identity/tenancy, catalog, inventory, customers, carts/checkout, orders, payments/ledger, fulfillment/dispatch, channels, notifications, analytics, AI tools/approvals, subscriptions, and audit/outbox. Modules expose service interfaces and own their persistence rules; external effects are adapters invoked through durable jobs/outbox events.

## Reliability and financial boundaries

Use PostgreSQL transactions, conditional updates/row locks, unique idempotency keys, immutable order/payment records, integer minor currency units, and a balanced double-entry ledger. Keep payment and fulfillment state machines separate. Critical asynchronous work moves through a transactional outbox with bounded retries and dead-letter visibility. Redis/Celery are planned for later work, not part of Sprint 1.

## Deployment boundary

Podman/Docker Compose runs the legacy bot, PostgreSQL, a one-shot migration service, and the commerce API for local development. Production environments must be separated into development, staging, and production. No production deployment or production data change is authorized by implementation work.