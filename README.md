# TrustiPay Central Ledger Backend (Queue-First)

TrustiPay is an offline-first peer-to-peer digital payment research prototype.

This backend receives transaction submissions from mobile apps, queues them durably in SQLite, then processes each transaction one-by-one through security verification and settlement checks before writing outcomes to the central ledger.

## Key Features

- FastAPI + SQLAlchemy + SQLite
- Queue-first asynchronous processing
- Separate online and offline batch ingestion endpoints
- Outbound security verification call (configurable HTTP POST)
- Post-security validation + fraud stub + additional checks hook
- Central ledger with approved/rejected/security_review outcomes
- Approved-only tamper-evident hash chain
- Device balance settlement for approved transactions
- Streamlit dashboard for queue flow and ledger observation
- Swagger/OpenAPI docs at `/docs` and `/openapi.json`

## Project Structure

```text
trustipay-ledger-backend/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── routers/
│   │   ├── transactions.py
│   │   └── devices.py
│   └── services/
│       ├── queue_service.py
│       ├── queue_processor_service.py
│       ├── security_service.py
│       ├── additional_checks_service.py
│       ├── validation_service.py
│       ├── fraud_service.py
│       ├── hash_service.py
│       └── ledger_service.py
├── docs/
│   ├── architecture.md
│   ├── api-contracts.md
│   ├── security-integration.md
│   └── processing-runbook.md
├── tests/
│   └── test_queue_flow.py
├── streamlit_dashboard.py
├── requirements.txt
└── README.md
```

## Quick Start

```bash
# 1) create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# 2) install dependencies
pip install -r requirements.txt

# 3) run API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 4) (optional) run dashboard in another terminal
streamlit run streamlit_dashboard.py
```

Open:

- Swagger UI: `http://localhost:8000/docs`
- OpenAPI: `http://localhost:8000/openapi.json`
- Streamlit Dashboard: `http://localhost:8501`

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./trustipay.db` | Database connection |
| `ENABLE_QUEUE_WORKER` | `true` | Enable in-process sequential queue worker |
| `QUEUE_POLL_INTERVAL_SECONDS` | `1.0` | Worker poll sleep when no jobs |
| `QUEUE_MAX_SECURITY_RETRIES` | `3` | Max retries for security transport/5xx failures |
| `QUEUE_RETRY_BACKOFF_SECONDS` | `2.0` | Retry backoff multiplier |
| `SECURITY_ENDPOINT_URL` | empty | External security verification endpoint |
| `SECURITY_TIMEOUT_SECONDS` | `5.0` | Security endpoint request timeout |

## API Summary

| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/transactions/online` | Enqueue one online transaction |
| `POST` | `/v1/transactions/offline-sync` | Enqueue offline batch (array) |
| `POST` | `/v1/transactions/submit` | Deprecated alias of `/online` |
| `GET` | `/v1/transactions/{tx_id}` | Get status (queue + ledger resolved) |
| `GET` | `/v1/transactions` | List settled ledger rows |
| `GET` | `/v1/transactions/queue` | Inspect queue rows |
| `GET` | `/v1/transactions/chain/verify` | Verify approved-only hash chain |
| `GET` | `/v1/devices/{device_id}/balance` | Get settled device balance |
| `GET` | `/v1/devices/{device_id}/ledger-sync` | Device reconciliation |
| `GET` | `/health` | Service health |

## Status Model

Public statuses:

- `queued`
- `processing`
- `security_review`
- `approved`
- `rejected`
- `duplicate`

### Eventual Consistency

Submission endpoints only enqueue work and return immediately.
Final settlement decisions are asynchronous; clients must poll `GET /v1/transactions/{tx_id}`.

## Example Requests

### Enqueue Online

```bash
curl -X POST http://localhost:8000/v1/transactions/online \
  -H "Content-Type: application/json" \
  -d '{
    "tx_id": "TXN-ONLINE-001",
    "sender_id": "DEV-ALICE",
    "receiver_id": "DEV-BOB",
    "timestamp": "2026-03-08T10:30:00Z",
    "amount": 150.00,
    "transaction_type": "QR",
    "device_type": "Pixel 8",
    "network_type": "offline",
    "phone_number": "+94771234567",
    "location": "Western Province",
    "prev_hash": "0000000000000000000000000000000000000000000000000000000000000000",
    "tx_hash": "<client-computed-hash>",
    "signature": "BYPASS"
  }'
```

### Enqueue Offline Batch

```bash
curl -X POST http://localhost:8000/v1/transactions/offline-sync \
  -H "Content-Type: application/json" \
  -d '[{...},{...}]'
```

## Processing Flow

1. Client submits online or offline batch item.
2. Server validates schema and enqueues as `queued`.
3. Background worker claims one queue row (`processing`).
4. Worker calls security endpoint via HTTP POST.
5. On security `PASS`: run additional checks, validation, fraud stub.
6. Write outcome into `central_ledger`:
   - `approved`: update balances and extend hash chain
   - `rejected` or `security_review`: no chain extension, no balance update
7. Queue row becomes `completed` with final status.

## Dashboard

`streamlit_dashboard.py` provides three views:

- `Flow Monitor`: queue state breakdown, pending jobs, and recent queue activity
- `Central Ledger`: filterable ledger table + approved chain preview
- `Device Balances`: latest settled balances per device

The dashboard reads from the same SQLite database (`DATABASE_URL`) used by the backend.

## Testing

Service integration tests (enqueue + processor + status resolution):

```bash
python -m unittest tests/test_queue_flow.py
```

## Documentation Index

- [Architecture](docs/architecture.md)
- [API Contracts](docs/api-contracts.md)
- [Security Integration](docs/security-integration.md)
- [Processing Runbook](docs/processing-runbook.md)
