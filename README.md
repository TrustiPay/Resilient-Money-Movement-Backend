# TrustiPay Central Ledger Backend (Asynchronous Fraud Callback Flow)

TrustiPay is an offline-first P2P payment backend built with FastAPI + SQLite.

This version supports two ingestion flows:

- Online transactions: written to central ledger immediately as `queued`, then sent to fraud component.
- Offline sync transactions: queued first, validated by worker, then sent to fraud component only if validations pass.

Final decision is applied through a callback endpoint from fraud component.

## Core Flows

### Online
1. `POST /v1/transactions/online`
2. Transaction inserted in `central_ledger` as `queued`
3. Queue worker dispatches transaction to fraud component
4. Fraud component calls `POST /v1/transactions/fraud-callback`
5. Callback updates central ledger to final status (`approved`/`rejected`/`security_review`)

### Offline
1. `POST /v1/transactions/offline-sync` (array payload)
2. Queue worker validates each transaction:
   - hash mismatch
   - signature
   - double spend
   - duplicate
   - central ledger balance
3. If rejected for reason other than insufficient balance:
   - write `rejected` to `central_ledger` with reason
4. If rejected for `INSUFFICIENT_FUNDS`:
   - keep queue item in `retry_balance` and retry later
5. If validation passes:
   - write/update `central_ledger` as `pending_fraud`
   - dispatch to fraud component
6. Fraud callback finalizes result and updates:
   - `central_ledger`
   - `device_transaction_history` (offline flow)

## API Summary

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/transactions/online` | Receive one online transaction |
| POST | `/v1/transactions/offline-sync` | Receive offline pending batch |
| POST | `/v1/transactions/fraud-callback` | Fraud component posts final decision |
| GET | `/v1/transactions/{tx_id}` | Get transaction status |
| GET | `/v1/transactions/queue` | Queue inspection |
| GET | `/v1/transactions` | Central ledger query |
| GET | `/v1/devices/{device_id}/local-history` | Offline device history mirror |
| GET | `/v1/devices/{device_id}/ledger-sync` | Device ledger sync from central ledger |
| GET | `/v1/devices/{device_id}/balance` | Device balance |
| GET | `/health` | Service health |

## Status Values

- `queued`
- `processing`
- `retry_balance`
- `pending_fraud`
- `approved`
- `rejected`
- `security_review`
- `duplicate`

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./trustipay.db` | DB connection |
| `ENABLE_QUEUE_WORKER` | `true` | Enable worker loop |
| `QUEUE_POLL_INTERVAL_SECONDS` | `1.0` | Poll interval |
| `QUEUE_MAX_SECURITY_RETRIES` | `3` | Max dispatch retries |
| `QUEUE_RETRY_BACKOFF_SECONDS` | `2.0` | Retry backoff |
| `FRAUD_ENDPOINT_URL` | empty | Fraud ingestion endpoint |
| `FRAUD_TIMEOUT_SECONDS` | `5.0` | Fraud dispatch timeout |

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Swagger: `http://localhost:8000/docs`
- OpenAPI: `http://localhost:8000/openapi.json`

## Documentation

- `docs/architecture.md`
- `docs/api-contracts.md`
- `docs/security-integration.md`
- `docs/processing-runbook.md`
