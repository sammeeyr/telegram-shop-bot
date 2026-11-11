# Order Lifecycle

## Sprint 3 implementation

Tenant-scoped customers, addresses, carts, orders, items, and payment attempts are implemented. Checkout snapshots product/variant names, SKU, product type, currency, unit price, line total, and shipping address. Physical lines reserve stock; digital lines reserve encrypted one-use assets. Checkout is transactional and idempotent per tenant key.

Orders carry separate payment and fulfillment states; each order item has its own fulfillment state. Catalog edits do not change order snapshots.

## Digital payment gate

Digital stock is encrypted at rest using `DIGITAL_ASSET_ENCRYPTION_KEY`, separate from the JWT key. Release refuses pending/failed/refunded orders and returns no plaintext over a public endpoint. The only settlement entry point is an internal `VerifiedPayment` service contract. It validates tenant/order, exact amount and currency, provider reference, and pending state. There is no public “mark paid” endpoint, and no real payment provider is integrated yet. Sprint 4 must verify provider settlement and webhook signatures before constructing verified evidence.

Tests prove pending orders cannot release assets, amount mismatch is rejected, verified payment unlocks reserved assets, and checkout/delivery retries do not duplicate orders or assets.

## Remaining lifecycle work

Refunds, COD, cancellation transitions, audit timelines, transactional outbox, customer self-service authentication, and channel-specific order sources remain unimplemented. Physical dispatch is Sprint 8.