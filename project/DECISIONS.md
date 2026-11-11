# Decisions

## Product Decisions

These decisions were supplied by product leadership on 2026-11-10 and govern implementation sequencing:

1. Build the shared commerce engine first. Telegram is one adapter, never the source of core business rules.
2. Prioritize financial and inventory integrity over dashboard breadth.
3. Give AI agents only controlled, schema-validated service tools; no direct database access or independent sensitive authorization.
4. Implement tenant isolation from the first platform schema, including service/API/job/cache/storage boundaries and PostgreSQL RLS.
5. Start logistics with internal riders, manual assignment, zones, tracking, and provider adapters; defer route optimization and advanced automation.
6. Deliver backend foundation and pass tenant-isolation acceptance before building the storefront.
7. After platform workflows are fully functional and tested, develop a paid developer API/MCP offering with payment-gated entitlements and usage controls.

## Sprint 1 Implementation Decisions

| Topic | Choice | Consequence |
| --- | --- | --- |
| Application | FastAPI modular monolith, separate `commerce_api` package | Existing Telegram bot remains independent until its channel sprint. |
| Persistence | PostgreSQL, SQLAlchemy async, Alembic | All platform schema changes are versioned migrations. |
| Identity | Global UUID users; tenant membership carries owner/admin/staff role | Same user may join multiple merchants; every request selects and verifies tenant membership. |
| Authentication | Argon2id passwords, short-lived JWT access tokens, hashed rotating refresh tokens | Email verification, recovery, MFA, and abuse limits remain hardening work. |
| Database access | Separate migration-owner and restricted runtime roles; forced RLS | Merchant clients never receive database credentials. |
| Tenancy | One tenant per merchant store initially | Future custom domains and multiple stores per merchant require explicit product modeling. |
| Developer product | Defer paid API/MCP until platform and API are stable | Requires metering, billing entitlements, quotas, audit, and support before sale. |
| PostgreSQL hosting | Neon is the preferred managed Postgres candidate; keep standard PostgreSQL portability | Pooled URL for API, direct URL for migrations; no Neon-only SQL in domain services. |
| File storage | Keep a private S3-compatible storage adapter | Evaluate Neon Object Storage for branch-coupled previews vs Cloudflare R2 for Cloudflare CDN/edge delivery. Never put license secrets in public buckets. |
| Bot protection | Turnstile is optional on public browser forms | Backend Siteverify only; it supplements but never replaces authentication, rate limiting, or payment verification. |
| Cloudflare D1 | Not the commerce system of record | SQLite semantics do not match this backend's PostgreSQL RLS, composite FK, and transactional-locking requirements. |

## Pending Decisions

- Production hosting/secret manager, backup ownership, SLOs, and operational owner.
- Verification, password recovery, MFA, and rate-limit policy.
- Migration of legacy bot customer/catalog/order data into tenant-scoped shared services.
- API commercial plans, quota units, overage/denial behavior, and MCP transport after core delivery.