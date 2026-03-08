# Processing Runbook

## Runtime Checklist

1. `DATABASE_URL` points to writable SQLite path.
2. `ENABLE_QUEUE_WORKER=true` for normal async processing.
3. `SECURITY_ENDPOINT_URL` configured to reachable service.
4. App starts cleanly and `/health` returns `status=ok`.

## Useful Operational Endpoints

- `GET /health` - service health + worker enabled flag
- `GET /v1/transactions/queue` - inspect queue state and retries
- `GET /v1/transactions/{tx_id}` - end-user status lookup
- `GET /v1/transactions/chain/verify` - approved chain integrity

## Common Scenarios

### Transactions stay in `queued`

- Check `ENABLE_QUEUE_WORKER` is true.
- Check application logs for worker startup message.
- Inspect queue via `/v1/transactions/queue`.

### Transactions cycle through retry

- Security endpoint may be down or timing out.
- Inspect `last_error`, `attempts`, and `next_attempt_at` from queue endpoint.
- Validate `SECURITY_ENDPOINT_URL` and timeout values.

### Many `security_review` outcomes

- Indicates repeated security integration failures or explicit security review responses.
- Check external security API behavior and response contract.

### Unexpected duplicate responses

- Duplicate means `tx_id` already exists in ledger or active queue.
- Validate mobile-side `tx_id` generation uniqueness.

## Deterministic Processing Guidance

For prototype determinism, run a single API process so only one in-process worker is active.

Example:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Avoid multiple parallel workers/processes unless queue locking is redesigned.

## Local Test Command

```bash
python -m unittest tests/test_queue_flow.py
```
