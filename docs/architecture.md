# Architecture

## Component View

```text
Mobile App
  |                    Fraud Component
  | POST /online       | POST /fraud-callback
  | POST /offline-sync |
  v                    v
FastAPI Router --> transaction_queue --> Queue Worker --> Fraud Dispatch (HTTP POST)
      |                    |                                  |
      |                    v                                  |
      +---------------> central_ledger <----------------------+
                           |
                           +--> device_balances (approved only)
                           |
                           +--> device_transaction_history (offline callback updates)
```

## Storage Responsibilities

- `transaction_queue`: ingestion durability, processing lifecycle, retry metadata.
- `central_ledger`: canonical transaction state and settlement audit.
- `device_balances`: settled balances.
- `device_transaction_history`: mirrored offline-device history updates after fraud callback.

## Queue States

- `queued`: accepted and waiting.
- `processing`: worker currently handling.
- `retry_wait`: temporary dispatch retry.
- `retry_balance`: offline transaction waiting for sufficient sender balance.
- `completed`: worker finished current phase (`pending_fraud`, `rejected`, `duplicate`).

## Central Ledger Statuses

- `queued`: online transaction persisted immediately.
- `pending_fraud`: submitted to fraud component and waiting callback.
- `approved`: final success, balances updated, chain extended.
- `rejected`: final reject with reason.
- `security_review`: review status from fraud callback.

## Flow Rules

### Online
- Ingestion writes `central_ledger(status=queued)` immediately.
- Worker dispatches to fraud endpoint.
- Callback finalizes status.

### Offline
- Ingestion writes queue only.
- Worker runs validation sequence:
  1. hash mismatch
  2. signature
  3. double spend
  4. duplicate
  5. central balance
- Reject reasons except `INSUFFICIENT_FUNDS` write immediate `rejected` ledger entry.
- `INSUFFICIENT_FUNDS` remains retriable via `retry_balance`.
- Passed validation moves to `pending_fraud` and waits callback.

## Hash Chain

- Only `approved` rows extend chain.
- `prev_hash` points to last approved `tx_hash`.
- Non-approved rows do not extend chain.
