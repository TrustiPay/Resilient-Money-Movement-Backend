# Security Integration

The worker performs security verification for each dequeued transaction before local settlement checks.

## Endpoint Configuration

- Env var: `SECURITY_ENDPOINT_URL`
- Timeout: `SECURITY_TIMEOUT_SECONDS` (default `5.0`)

If `SECURITY_ENDPOINT_URL` is empty or unreachable, transport failure handling applies.

## Outbound Request

- Method: `POST`
- URL: `SECURITY_ENDPOINT_URL`
- Body: full transaction payload JSON as submitted by mobile

## Expected Response Contract

```json
{
  "decision": "PASS | FAIL | REVIEW",
  "reason": "optional string"
}
```

Decision semantics:

- `PASS`: continue to additional/local checks
- `FAIL`: reject transaction
- `REVIEW`: mark `security_review`

## Retry Policy

Retries are applied only for transport-level failures or HTTP 5xx responses.

Config:

- `QUEUE_MAX_SECURITY_RETRIES` (default `3`)
- `QUEUE_RETRY_BACKOFF_SECONDS` (default `2.0`)

Backoff schedule:

- `next_attempt_at = now + QUEUE_RETRY_BACKOFF_SECONDS * attempts`

## Failure Mapping

- Transport/5xx failures before max retries: queue state -> `retry_wait`
- Transport/5xx failures after max retries: ledger status -> `security_review`, reason `SECURITY_UNAVAILABLE`
- HTTP 4xx from security endpoint: treated as security `FAIL`
- Invalid JSON/decision response: treated as transport integration failure and retried

## Security Data Captured in Queue

The queue row stores:

- `security_decision`
- `security_reason`
- `last_error`
- retry metadata (`attempts`, `max_attempts`, `next_attempt_at`)

This supports audit and troubleshooting without losing processing context.
