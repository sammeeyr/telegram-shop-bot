# Payment Integrations

## Current implementation boundary

Sprint 3 adds provider-neutral `PaymentAttempt` rows and independent order payment status. Checkout creates a pending attempt; there is still no provider adapter, payment initialization endpoint, webhook route, or actual settlement. The legacy Telegram bot's Crypto Pay records are separate and do not settle commerce orders.

`record_verified_payment` is an internal service boundary. It validates tenant/order, exact amount and currency, provider reference, and pending state before marking an order paid. It is not exposed as an HTTP endpoint. Never accept a browser, Telegram, or admin-supplied “paid” boolean as evidence.

## Planned provider contract

Build provider adapters behind one commerce payment service. Initialize payments server-side, persist merchant/provider/reference/amount/currency/idempotency data, and verify settlement server-side. Webhook event IDs must be unique and processed idempotently; verify each provider signature using the raw request bytes and its current official specification. Validate amount, currency, reference and merchant before changing payment state. Frontend redirects, Telegram callbacks, screenshots, and client claims are never payment proof.

Planned methods: Paystack, Flutterwave, manual bank transfer reconciliation, cash on delivery, and optional Crypto Pay. Keep merchant proceeds, platform revenue, COD collections, refunds, and settlements separate. Reconciliation and balanced ledger entries are required before production money movement.

## Authoritative references for implementation

- [Paystack Transaction API](https://paystack.com/docs/api/transaction/)
- [Paystack Webhooks](https://paystack.com/docs/payments/webhooks/)
- [Flutterwave Standard Checkout](https://developer.flutterwave.com/docs/flutterwave-standard-1)
- [Flutterwave Webhooks](https://developer.flutterwave.com/docs/webhooks)
- [Telegram Bot API](https://core.telegram.org/bots/api)

Re-check official documentation when implementing each integration; signature formats and settlement semantics are provider-specific and can change. Do not claim a provider is supported until it has integration tests and reconciliation evidence.