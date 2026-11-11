# Dispatch Engine

## Status and scope

No physical dispatch engine exists in the shared platform. The old bot only sends digital purchases in Telegram. Logistics is planned for Sprint 8 and deliberately starts with internal riders, manual assignment, delivery zones, tracking, and provider adapters. Route optimization and advanced auto-dispatch wait until core workflows are proven.

## Initial domain

Add tenant-owned delivery zones/rates, rider registration and availability, dispatch assignments, shipments, delivery events, attempts, proof of delivery, OTP verification, and COD collection/reconciliation. Keep payment and fulfillment status separate. A `LogisticsProvider` adapter must isolate third-party booking/tracking APIs; no courier is hardcoded into order logic. The responsive rider PWA is a channel over the same dispatch services.

All assignment, tracking, attempt, proof, and cash reconciliation actions need actor/time audit records. Provider calls and notifications must be idempotent, retryable, and outbox-driven. Keep route optimization out of the first delivery workflow.