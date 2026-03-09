# Processing Runbook

## Startup Checklist

1. `DATABASE_URL` points to writable DB.
2. `ENABLE_QUEUE_WORKER=true`.
3. `FRAUD_ENDPOINT_URL` configured.
4. `/health` responds with `status=ok`.

## Operational Endpoints

- `GET /health`
- `GET /v1/transactions/queue`
- `GET /v1/transactions/{tx_id}`
- `GET /v1/transactions/chain/verify`

## Common Scenarios

### Transaction stuck in `queued`
- Worker disabled or crashed.
- Check startup logs and queue endpoint.

### Transaction in `retry_wait`
- Fraud endpoint unreachable/failed.
- Check `last_error`, `attempts`, `next_attempt_at`.

### Offline transaction in `retry_balance`
- Sender balance is still insufficient.
- Item will be retried automatically.
- Once funds are available and item reprocessed, it can move to `pending_fraud`.

### Callback received but no state change
- Verify `tx_id` exists in queue history.
- Ensure callback `decision` is one of `APPROVE|REJECT|REVIEW`.

## Recovery Guidance

- For failed dispatch bursts, restore fraud endpoint and let retries continue.
- For data correction, use DB backup and replay callback with same `tx_id` (idempotent behavior expected).
- Keep single API worker process in prototype mode for deterministic ordering.
