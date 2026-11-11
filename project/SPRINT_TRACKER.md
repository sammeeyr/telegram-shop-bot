# Sprint Tracker

Sprints are sequential. Do not start Sprint 2 until Sprint 1's PostgreSQL tenant-isolation acceptance test passes in CI.

## Sprint 1: Foundation and Tenancy

Implementation and local PostgreSQL acceptance are complete. Development stack runs under Podman Desktop.

- [x] FastAPI app with versioned `/api/v1` routes and OpenAPI.
- [x] PostgreSQL async SQLAlchemy database layer and initial Alembic migration.
- [x] Merchant onboarding, account registration/login, short-lived access tokens, rotating refresh tokens.
- [x] Tenant memberships, owner/admin/staff RBAC, platform-admin promotion command.
- [x] Forced PostgreSQL RLS on current tenant-owned tables and separate runtime/migration roles.
- [x] Docker development services and PostgreSQL CI workflow.
- [x] API acceptance tests for two merchants, cross-tenant denial, RBAC, and refresh-token replay.
- [x] Direct PostgreSQL RLS test implemented against the restricted runtime role.
- [x] Run the direct PostgreSQL RLS test using the restricted runtime role: `1 passed` on 2026-11-10.
- [x] Verify API readiness against PostgreSQL: `/health/ready` returned `ready` on 2026-11-10.
- [ ] Review/approve production operational prerequisites; no production deployment authorized.

**Acceptance:** API isolation and direct PostgreSQL RLS checks pass. The API tests cover two merchant onboardings and cross-tenant access denial; the PostgreSQL test confirms a non-superuser runtime role sees only its tenant. Production approval remains separate.

## Next sprints

### Sprint 2: Products and Inventory

Implementation and local PostgreSQL acceptance are complete under Podman Desktop.

- [x] Tenant-scoped categories, products, variants/SKUs, and publication.
- [x] Warehouses and on-hand/reserved/available/safety quantities.
- [x] Idempotent receipts, movements, adjustments, returns, and transfers.
- [x] Atomic reservations, release, deduction, expiry sweep, and safety-stock enforcement.
- [x] PostgreSQL concurrency test for two buyers competing for the last unit.
- [x] Apply migrations `0002_catalog_inventory` and `0003_stock_transfers` to the local PostgreSQL database.
- [x] Run full test suite with PostgreSQL integration enabled: `28 passed, 0 skipped` on 2026-11-10.
- [x] Verify API readiness after migration: `/health/ready` returned `ready` on 2026-11-10.

**Acceptance:** tenant-scoped catalog and inventory APIs work; concurrent reservations cannot oversell the last unit; expiry releases reservations; direct SQL remains tenant-isolated. Sprint 2 acceptance passed locally. No production deployment is authorized.

### Sprint 3: Commerce and Orders

Implementation and local PostgreSQL validation are complete.

- [x] Tenant-scoped customers, addresses, carts, orders, items, and payment attempts.
- [x] Transactional, idempotent checkout with immutable price/product/address snapshots.
- [x] Separate payment/fulfillment states and per-line fulfillment state.
- [x] Physical stock reservations and encrypted digital asset reservation.
- [x] Digital release denied before verified payment; amount/currency mismatch rejected.
- [x] Direct PostgreSQL RLS coverage includes actual order and digital-asset rows.
- [x] Full suite against Podman PostgreSQL: `30 passed, 0 skipped` on 2026-11-10.
- [x] Alembic metadata parity: no new upgrade operations detected.

**Acceptance:** physical checkout reserves stock; digital fulfillment remains locked until internal provider-verified payment; snapshots remain immutable; all new rows are tenant-isolated. No payment provider is integrated yet.

| Sprint | Scope | Status | Gate |
| --- | --- | --- | --- |
| 2 | Products and inventory | Complete | Passed locally; keep CI as merge gate |
| 3 | Commerce and orders | Complete | Passed locally; keep CI as merge gate |
| 4 | Payments | Not started | Sprint 3 acceptance |
| 5 | Telegram channel | Not started | Shared commerce flows |
| 6 | Storefront and sales pages | Not started | Shared commerce flows |
| 7 | WhatsApp sales | Not started | Consent/webhook review |
| 8 | Dispatch and logistics | Not started | Orders and inventory stable |
| 9 | Controlled AI agents | Not started | Approved services/tools |
| 10 | Security, testing, production readiness | Not started | All core workflows |

The paid developer API/MCP product is a later phase after the platform API is stable and has authentication, entitlements, payment-gated access, and usage metering.