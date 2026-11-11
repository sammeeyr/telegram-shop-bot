# Deployment Guide

## Local Development

The repository supports Python 3.11+ and Docker. Copy `.env.example` to `.env`, generate a unique `JWT_SECRET_KEY` of at least 32 characters, and replace development database passwords before sharing the environment. Example values are placeholders for local work only.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
docker compose up -d postgres
alembic upgrade head
uvicorn commerce_api.asgi:app --reload
```

The API is at `http://localhost:8000`; OpenAPI is at `/docs`, liveness at `/health/live`, readiness at `/health/ready`. API connections use the restricted runtime role; migrations use `commerce_migrator`.

For hosted PostgreSQL, Neon is compatible with the current driver and migrations: set `COMMERCE_DATABASE_URL` to a pooled connection for API traffic and `MIGRATION_DATABASE_URL` to a direct, non-pooled connection. Keep TLS enabled. Cloudflare Hyperdrive is only needed if the backend runs on Workers.

`podman compose up -d --build postgres migrate api` runs the backend services under Podman Desktop. `docker compose up --build` is also supported. The bot remains on its separate SQLite data volume and is not yet a commerce API channel adapter.

Promote a registered operator to platform administrator with:

```powershell
commerce-api promote-platform-admin operator@example.com
```

## Tests and Migrations

Run `python -m pytest`. API tests use isolated SQLite. To run RLS tests against Podman PostgreSQL, set `TEST_DATABASE_URL=postgresql+asyncpg://commerce_runtime:runtime_dev_only@localhost:5432/commerce`. CI performs this path automatically. Alembic migrations run as `commerce_migrator`; never run API requests with the migration credential. Back up production data and test forward/rollback plans before release.

## Deployment Policy

Development, staging, and production must have separate databases, credentials, signing keys, storage, and provider accounts. Do not deploy to production or modify production data without explicit approval. Before a production launch, add secret-manager handling, TLS/ingress, backup/restore runbooks, rate limiting, monitoring/alerts, dependency scanning, and reviewed migration/rollback procedures. Railway compatibility is a target, not a validated production deployment yet.

When file uploads are introduced, choose Neon Object Storage for branch-coupled previews or Cloudflare R2 for Cloudflare CDN/edge delivery behind the same private S3 adapter. Verify each provider's S3 compatibility details. Turnstile is optional for public browser forms; always use backend Siteverify and keep authentication, authorization, rate limits, and payment verification separate.