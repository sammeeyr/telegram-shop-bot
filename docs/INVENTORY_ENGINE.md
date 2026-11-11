# Inventory Engine

## Sprint 2 implementation

The shared backend now has tenant-owned categories, products, variants/SKUs, warehouses, per-warehouse inventory balances, reservations, and append-only stock movement records. Balance fields distinguish on-hand, reserved, safety stock, and computed available quantity. Product prices use integer minor units; stock quantities use `NUMERIC(18,3)`.

Movement operations include receipts, signed adjustments, customer returns, paired warehouse transfers, reservations, releases, expiry, and deductions. Mutations and movement rows are committed in the request transaction. Idempotency keys are tenant-scoped; transfer keys produce stable paired movement identifiers.

## Concurrency and isolation

Reservation uses a conditional database update requiring `on_hand - reserved - safety_stock >= requested quantity`. PostgreSQL rechecks the predicate after row-lock waits, preventing simultaneous checkouts from overselling the last unit. Transfers lock source and destination balances in deterministic warehouse order and atomically update both. Tenant IDs are included in every row, composite foreign keys, query, and forced RLS policy.

The PostgreSQL integration test races two independent transactions against one unit and asserts exactly one succeeds. It also verifies cross-tenant invisibility and expiry releasing reservations. The expiry sweep is currently an explicit bounded API operation; a scheduled worker is future infrastructure.

## Boundaries

Order/checkout integration, reservation creation as part of order placement, stock-location bins, receiving workflows, and movement approvals remain future work. The legacy bot's digital stock remains separate and is not shared with this inventory engine.