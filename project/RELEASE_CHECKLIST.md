# Release Checklist

## Before release

- [ ] Review the diff and confirm no secrets, customer data, or stock contents are committed.
- [ ] Run `python -m pytest` and add regression coverage for behavior changes.
- [ ] Confirm `.env.example`, README, and deployment settings match the release.
- [ ] Review dependency changes and supported Python/database versions.
- [ ] Apply Alembic migrations with the migration role; verify the API uses only the restricted runtime role.
- [ ] Pass the two-merchant API and direct PostgreSQL RLS acceptance tests in CI.
- [ ] Confirm every new tenant-owned table has a tenant FK, RLS policy, and cross-tenant tests.
- [ ] Back up the production database and verify the restore procedure.
- [ ] For schema changes, prepare and test a migration/rollback plan.
- [ ] Test payment changes against Crypto Pay testnet; verify no real-money credentials are used in tests.
- [ ] Confirm admin IDs, production tokens, currency, deposit bounds, and testnet/mainnet mode.
- [ ] Verify purchase atomicity, ownership checks, HTML escaping, and delivery recovery for affected paths.
- [ ] Confirm a single active bot/poller instance unless coordination has been added.

## Deploy and observe

- [ ] Deploy only to the explicitly approved environment and verify API health, database access, and tenant authorization.
- [ ] Exercise a representative catalog action and purchase path; exercise a small testnet payment when relevant.
- [ ] Watch API/database health, queue/payment errors, delivery failures, disk usage, and tenant-scoped alerts.
- [ ] Record release version, deployment time, operator, and any follow-up issues.

## Rollback

- [ ] Stop or roll back the application version without deleting persistent data.
- [ ] Restore database backup only when necessary and reconcile orders, deposits, and ledger entries before reopening sales.
- [ ] Rotate any credentials exposed during deployment and document the incident.