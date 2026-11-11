# Test Strategy

## Current coverage

Run `python -m pytest`. The legacy bot suite still tests money, services, payment polling, and fake Telegram flows. `tests/test_commerce_api.py` tests onboarding, two-tenant API isolation, role checks, catalog publication, inventory operations, idempotency, and refresh-token replay rejection. PostgreSQL tests directly verify forced RLS, expiry, and concurrent reservation of the final unit.

The direct PostgreSQL test skips when `TEST_DATABASE_URL` is unset. CI starts PostgreSQL, applies Alembic migrations as the migration role, grants the restricted runtime role table access, then runs the full suite. Local SQLite API tests do not prove RLS behavior.

## Required coverage by sprint

- Sprint 1-2: API and raw PostgreSQL tenant isolation, RBAC, refresh rotation, composite tenant foreign keys, inventory constraints, expiry, and last-unit concurrency.
- Commerce/inventory: money minor-unit precision, balanced ledger, atomic last-unit reservations, expiry/release, oversell concurrency.
- Payments: raw-body signature verification, amount/currency/merchant validation, duplicate/out-of-order webhooks, idempotency, refunds and reconciliation.
- Orders/dispatch: independent payment/fulfillment transitions, COD collection reconciliation, unauthorized transitions, proof and tracking audit.
- Channels: identical shared service outcomes, consent/template rules, webhook replay, order-to-delivery workflows.
- AI: tool schema/allowlist, tenant authorization, prompt injection, approval, human takeover, usage caps and audit.
- Release: HTTPX API tests, PostgreSQL constraints/RLS, provider mocks, and Playwright end-to-end tests when a frontend exists.

Never use production credentials or real payment/courier actions in automated tests. Every fixed regression gets a focused test.