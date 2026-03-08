# Architecture

## High-Level Components

```text
Mobile App (online submit / offline batch sync)
                  |
                  v
        FastAPI Transaction Router
                  |
                  v
         transaction_queue (SQLite)
                  |
                  v
     Sequential Queue Worker (single process)
                  |
                  v
      External Security Endpoint (HTTP POST)
                  |
     PASS --------+--------- FAIL/REVIEW/ERROR
      |                         |
      v                         v
Post-security checks      Reject/Review outcome
(validation + fraud)              |
      |                           v
      +------------------> central_ledger (SQLite)
                                  |
                                  v
                          Device balance updates
                         (approved only)
```

## Persistence Model

- `transaction_queue`: durable queue records and processing lifecycle.
- `central_ledger`: settlement and audit history for processed outcomes.
- `device_balances`: current settled balances per device.

## Queue State Lifecycle

- `queued`: accepted by API and waiting for processing.
- `processing`: worker currently handling the transaction.
- `retry_wait`: security transport/5xx retry delay.
- `completed`: worker finished and set final status (`approved`, `rejected`, `security_review`, `duplicate`).

## Transaction Outcome Rules

- Security `FAIL` -> `rejected` in ledger.
- Security `REVIEW` -> `security_review` in ledger.
- Security transport error retries exhausted -> `security_review` in ledger.
- Security `PASS` + all checks passed -> `approved` in ledger and balances updated.
- Duplicate detection before processing completion -> queue final status `duplicate`.

## Hash Chain Rules

- Only `approved` ledger rows extend the chain.
- Approved transaction:
  - `prev_hash = last approved tx_hash` (or genesis `0*64`)
  - `tx_hash = SHA256(canonical_payload + prev_hash)`
- Non-approved transaction:
  - `prev_hash = NULL`
  - `tx_hash = SHA256(canonical_payload + "")`

## Concurrency Model

- Designed for prototype determinism with a single in-process worker.
- Worker processes FIFO by ascending `queue_id`, one transaction per cycle.
- Multi-process distributed workers are out of scope for this version.
