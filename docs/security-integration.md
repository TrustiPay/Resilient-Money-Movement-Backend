# Fraud Integration (Callback Mode)

This file documents the external fraud component integration.

## Outbound Dispatch (Server -> Fraud Component)

- Method: `POST`
- URL: `FRAUD_ENDPOINT_URL`
- Timeout: `FRAUD_TIMEOUT_SECONDS`
- Payload:

```json
{
  "trace_id": "TRACE-ABC123",
  "source_type": "online | offline_sync",
  "transaction": { "...full tx payload..." }
}
```

Dispatch errors:
- HTTP/network/timeout and HTTP 4xx/5xx are treated as dispatch failures.
- Queue state moves to `retry_wait`.
- On max retry exhaustion, transaction is marked `rejected` with `FRAUD_DISPATCH_FAILED`.

## Inbound Callback (Fraud Component -> Server)

- Method: `POST`
- Path: `/v1/transactions/fraud-callback`
- Body:

```json
{
  "tx_id": "TXN-001",
  "decision": "APPROVE | REJECT | REVIEW",
  "reason_code": "optional"
}
```

Decision mapping:
- `APPROVE` -> ledger `approved` (if balance valid at settlement point)
- `REJECT` -> ledger `rejected`
- `REVIEW` -> ledger `security_review`

Offline callback side effect:
- Updates `device_transaction_history` table for device sync visibility.

## Required Reliability Guarantees

- Fraud callback endpoint is idempotent by `tx_id`.
- If a final state already exists, callback returns existing state without duplicate writes.
- Queue and ledger must carry `trace_id` for full audit chain.
