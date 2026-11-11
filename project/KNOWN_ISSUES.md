# Known Issues

Track actionable defects with reproduction steps, impact, owner, and tests. Do not use this page as an incident record.

## Sprint 1 and platform gaps

- Sprint 1 PostgreSQL RLS acceptance passed locally under Podman Desktop on 2026-11-10; retain the CI PostgreSQL job as the merge gate.
- Sprint 2 full suite and live PostgreSQL concurrency/RLS tests passed locally under Podman Desktop on 2026-11-10 (`28 passed, 0 skipped`).
- Sprint 3 checkout, immutable snapshots, digital payment gating, full suite, and direct PostgreSQL RLS tests passed locally under Podman Desktop on 2026-11-10 (`30 passed, 0 skipped`).
- Email verification, password reset, MFA, authentication rate limiting, and suspicious-login monitoring are not implemented.
- Membership management adds only already-registered users; invitation delivery is not implemented.
- API request IDs, structured tenant-aware logs, metrics, and alerting are not implemented.
- PostgreSQL RLS currently covers only `tenants` and `tenant_memberships`; each future tenant-owned table must add its own policy in the creating migration.
- Sprint 3 commerce APIs are implemented; payment providers/webhooks, refunds, customer self-service auth, outbox, and payment/fulfillment timelines are not yet available.
- Digital asset encryption requires `DIGITAL_ASSET_ENCRYPTION_KEY`; it is intentionally absent from committed defaults and must be generated per environment.
- The new backend has no payments, ledger, channels, dispatch, or AI yet.
- The legacy Telegram bot still uses a separate SQLite database and is not connected to shared commerce services.
- Production deployment, restore validation, secret management, and external security review have not been performed.