# Tenant Isolation

## Current implementation

Sprint 1 introduces global `users`, merchant `tenants`, and tenant-scoped `tenant_memberships`. Onboarding creates an owner and membership in the same transaction. The tenant selector is `X-Tenant-ID`; the backend checks membership and role on each request before domain access. Owner/admin/staff capabilities are enforced in FastAPI dependencies and membership operations.

The Alembic migration enables and forces RLS on `tenants` and `tenant_memberships`. Context is set with transaction-local `set_config` only after user authentication; tenant membership is checked before tenant handlers proceed. The application connects as `commerce_runtime`, not as the table owner or a `BYPASSRLS` role. The `commerce_migrator` account is only for migrations. Never give either credential to a merchant or frontend.

RLS is defense in depth around the trusted backend. Runtime DB credentials remain privileged service credentials; do not expose them to customers or third-party integrations. Application authorization and resource-level checks are still required. CI tests both API-level isolation and direct SQL visibility using the restricted runtime role and correctly scoped context.

## Rules for every future module

- Every merchant-owned row has a non-null tenant FK, tenant-aware indexes/uniqueness, and an RLS policy in its first migration.
- Resolve tenant from authenticated membership, never from a client-supplied ID alone. Carry an immutable tenant context into services, repositories, jobs, cache keys, object-storage paths, and audit records.
- Recheck resource ownership in service operations. Cross-tenant lookup should not reveal resource existence.
- Background jobs and outbox workers must carry and validate tenant context; no ambient tenant state may leak across pooled connections or tasks.
- Cross-tenant platform operations require explicit platform-admin authorization and audit events.
- Tests must cover API reads/writes, raw SQL under the runtime role, connection reuse/context reset, background jobs, and cache/storage key separation.

## Current boundary and migration

Only tenant and membership tables exist in the commerce database today. The legacy bot uses a separate database and global administrator IDs. No merchant commerce data is shared between those systems yet. On migration, assign every imported record to an explicit tenant and verify foreign keys, financial history, and isolation before opening access.