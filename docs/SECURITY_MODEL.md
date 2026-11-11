# Security Model

## Assets and trust boundaries

Protect account credentials, access/refresh tokens, tenant data, future inventory and customer records, payment credentials, ledger entries, channel credentials, and audit history. Trust boundaries include merchant users, platform operators, channel providers, payment providers, workers, object storage, and PostgreSQL.

## Sprint 1 controls

- Passwords use Argon2id via `pwdlib`; raw passwords are never persisted or returned.
- JWT access tokens are short-lived. Refresh tokens are random, stored only as SHA-256 hashes, rotated on use, and revoked on logout.
- Registration/onboarding validates inputs with Pydantic. Tenant slugs/emails have database uniqueness protections.
- Tenant membership and role are checked per request. Owner/admin/staff actions are distinct; platform-admin elevation is performed via a server-side CLI command, never public API.
- Forced RLS protects tenant and membership tables. API access uses a non-owner, non-superuser runtime DB role; migration credentials are separate.
- Forced RLS covers all Sprint 1-3 tenant-owned tables. Digital assets are Fernet-encrypted at rest with `DIGITAL_ASSET_ENCRYPTION_KEY`, separate from JWT signing.
- Secrets are environment-driven. `.env.example` contains placeholders only and `.env` is ignored.

## Required platform invariants

Never trust payment redirects, screenshots, model output, channel payloads, or client tenant IDs as authority. Verify payment server-side and signature-check webhooks against raw request bytes. Enforce inventory/financial constraints in transactional domain services. AI tools may call only allowlisted services and may not directly mutate payment, stock, refund, or rider assignment state. Use private object storage and expiring signed URLs. Audit privilege and financial changes.

## Sprint 1 gaps

Email verification, password reset, MFA, login/onboarding rate limits, token-family replay detection, secret-manager integration, dependency scanning, structured request/tenant logging, and formal incident monitoring are not implemented. Object storage and Turnstile are not wired. If Turnstile is used on public browser forms, backend Siteverify validation is mandatory; it does not replace authentication or payment verification. The API is not production-ready until these controls, PostgreSQL CI, backups/restore, operational review, and TLS deployment are complete. Never deploy to production under this task.

## Incident response

Revoke or rotate exposed credentials, restrict database access, preserve logs, identify affected tenants and records, reconcile financial events, restore only from verified backups, and record actions and follow-ups. Never include secrets or sensitive customer data in issue reports.