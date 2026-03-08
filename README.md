# TrustiPay Central Ledger Backend

Offline-first P2P digital payment settlement backend built with **Python + FastAPI + SQLite**.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the server (from the project root)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Browse to:
- **Swagger UI** → http://localhost:8000/docs
- **ReDoc**       → http://localhost:8000/redoc
- **OpenAPI JSON**→ http://localhost:8000/openapi.json

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/transactions/submit` | Submit transaction for settlement |
| `GET`  | `/v1/transactions/{tx_id}` | Get transaction status |
| `GET`  | `/v1/transactions` | Full ledger export (with filters) |
| `GET`  | `/v1/transactions/chain/verify` | Verify hash chain integrity |
| `GET`  | `/v1/devices/{device_id}/balance` | Get device balance |
| `GET`  | `/v1/devices/{device_id}/ledger-sync` | Sync device transaction history |
| `GET`  | `/v1/devices` | List all devices |
| `GET`  | `/health` | Health check |

---

## Example: Submit a Transaction

```bash
curl -X POST http://localhost:8000/v1/transactions/submit \
  -H "Content-Type: application/json" \
  -d '{
    "tx_id":            "TXN-001",
    "sender_id":        "DEV-ALICE",
    "receiver_id":      "DEV-BOB",
    "timestamp":        "2024-06-01T10:30:00Z",
    "amount":           150.00,
    "transaction_type": "QR",
    "device_type":      "Samsung Galaxy S23",
    "network_type":     "offline",
    "phone_number":     "+94771234567",
    "location":         "Western Province",
    "prev_hash":        "0000000000000000000000000000000000000000000000000000000000000000",
    "tx_hash":          "placeholder",
    "signature":        "BYPASS"
  }'
```

Response:
```json
{"tx_id": "TXN-001", "status": "approved", "trace_id": "TRACE-ABC123"}
```

---

## Project Structure

```
trustipay-ledger-backend/
├── app/
│   ├── main.py              # FastAPI app + lifespan
│   ├── database.py          # SQLAlchemy engine + session
│   ├── models.py            # ORM models (central_ledger, device_balances)
│   ├── schemas.py           # Pydantic request/response models
│   ├── routers/
│   │   ├── transactions.py  # POST /submit, GET /{tx_id}, GET / (full ledger)
│   │   └── devices.py       # GET /balance, GET /ledger-sync
│   └── services/
│       ├── validation_service.py  # Full validation pipeline
│       ├── fraud_service.py       # Mock fraud detection engine
│       ├── hash_service.py        # SHA-256 hash chain logic
│       └── ledger_service.py      # Atomic settlement orchestrator
├── requirements.txt
└── README.md
```

---

## Validation Pipeline

```
Mobile Payload
     │
     ▼
1. Schema Validation      ← Pydantic
2. Duplicate Check        ← tx_id uniqueness
3. Signature Verify       ← ECDSA stub (use "BYPASS" for testing)
4. Hash Recompute         ← SHA-256 integrity check
5. Balance Computation    ← Server-computed (never trusted from client)
6. Balance Validation     ← Reject if sender insufficient
7. Fraud Feature Build    ← Combine payload + balances
8. Fraud Detection        ← APPROVE / REJECT / REVIEW
9. Atomic Settlement      ← Ledger + balance update
```

---

## Fraud Detection Rules (Mock)

| Condition | Decision | Reason Code |
|-----------|----------|-------------|
| amount > 50,000 | REJECT | AMOUNT_EXCEEDS_LIMIT |
| newbal_sender < 0 | REJECT | INSUFFICIENT_FUNDS |
| amount > 10,000 AND network=offline | REVIEW | HIGH_VALUE_OFFLINE |
| location empty/unknown | REVIEW | MISSING_LOCATION |
| All others | APPROVE | — |

Replace `fraud_service.py` with your ML model to upgrade from stub to production.

---

## Hash Chain

Only **approved** transactions extend the chain:

```
Genesis (0x000...000)
    │
    └─► TX-001.tx_hash ◄── prev_hash=genesis
           │
           └─► TX-002.tx_hash ◄── prev_hash=TX-001.tx_hash
                  │
                  └─► TX-003.tx_hash ◄── ...
```

Rejected/review transactions store `prev_hash = NULL` and do not extend the chain.

Verify chain integrity: `GET /v1/transactions/chain/verify`
