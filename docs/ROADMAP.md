# Roadmap

This is a planning document, not a commitment or release schedule. Priorities and dates require maintainer approval.

## Delivery order

1. Foundation and tenancy: FastAPI, PostgreSQL, Alembic, auth, tenant membership/RBAC, RLS, onboarding, CI.
2. Products and inventory: catalog, variants, warehouses, movement ledger, reservations and concurrency.
3. Commerce and orders: customers, addresses, carts, checkout, immutable snapshots, discounts and timelines.
4. Payments: Paystack, Flutterwave, bank transfer, COD, webhooks, refunds, settlements and balanced ledger.
5. Telegram: multi-tenant bot routing and Telegram Web Apps using shared services.
6. Storefront and sales pages: Next.js storefronts, custom domains, campaigns and direct checkout.
7. WhatsApp: official Cloud API, verified webhooks, consent/window rules and shared inbox.
8. Dispatch and logistics: internal riders, manual assignment, zones, tracking, COD reconciliation, then provider adapters.
9. AI agents: five controlled specialists, tools, approvals, human takeover and usage monitoring.
10. Security, testing and production readiness: hardening, observability, load/chaos tests, operational runbooks and release gates.

Sprints are sequential. Each requires plan, migration, service, API/integration, UI where relevant, automated tests, regression fixes, documentation, and acceptance evidence before the next sprint starts.

## Later developer product

After the platform API is stable, documented, versioned, and production-tested, evaluate a paid developer offering: scoped API credentials, plan entitlements, payment-gated access, usage metering/quotas, billing/reconciliation, developer docs/SDKs, and an MCP server that delegates to the same allowlisted API/service contracts. This phase is after the ten platform sprints; do not sell or expose an unmetered or unstable API/MCP server.