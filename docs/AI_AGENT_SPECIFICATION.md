# AI Agent Specification

## Status

AI implementation is planned for Sprint 9. No model provider, agent runtime, or AI action is currently operational. The planned specialists are Sales, Customer Service, Inventory, Dispatch, and Business Intelligence.

## Control model

Agents receive only structured, schema-validated, allowlisted tools backed by tenant-scoped business services. No direct database access, arbitrary SQL, shell, or unrestricted network tools. Validate actor/tenant/resource permissions on every tool call. Treat customer messages, catalog text, files, and retrieved context as untrusted prompt-injection input.

AI must never independently authorize refunds, change payment state, alter inventory, or assign riders. Sensitive operations require human approval; customer order/tracking answers must come from verified services. Support immediate human takeover. Log tool arguments/results safely, approvals, model/version, tenant, user, cost, and outcome without storing unnecessary sensitive context. Enforce quotas, consent, data minimization, timeouts, fallback behavior, and redaction.

Before release, test prompt injection, cross-tenant access, tool schema rejection, authorization bypass, hallucinated tracking/payment claims, approval requirements, human takeover, and usage accounting. AI is an assistant, not a source of truth or a transaction authority.