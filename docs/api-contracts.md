# API Contracts

Base URL examples assume `http://localhost:8000`.

## Shared Transaction Payload

```json
{
  "tx_id": "TXN-001",
  "sender_id": "DEV-A",
  "receiver_id": "DEV-B",
  "timestamp": "2026-03-09T10:30:00Z",
  "amount": 100.0,
  "transaction_type": "QR",
  "device_type": "Phone",
  "network_type": "offline",
  "phone_number": "+94770000000",
  "location": "Western Province",
  "prev_hash": "....",
  "tx_hash": "....",
  "signature": "BYPASS"
}
```

## Public Status Values

- `queued`
- `processing`
- `retry_balance`
- `pending_fraud`
- `approved`
- `rejected`
- `security_review`
- `duplicate`

## 1) Online Ingestion

- `POST /v1/transactions/online`
- Body: shared transaction payload
- Response:

```json
{
  "tx_id": "TXN-001",
  "status": "queued",
  "trace_id": "TRACE-ABC123"
}
```

## 2) Offline Batch Sync

- `POST /v1/transactions/offline-sync`
- Body: array of shared transaction payloads
- Response:

```json
{
  "total": 2,
  "queued": 1,
  "duplicates": 1,
  "items": [
    {"tx_id": "TXN-001", "status": "duplicate", "trace_id": null},
    {"tx_id": "TXN-002", "status": "queued", "trace_id": "TRACE-XYZ"}
  ]
}
```

## 3) Fraud Decision Callback

- `POST /v1/transactions/fraud-callback`
- Body:

```json
{
  "tx_id": "TXN-001",
  "decision": "APPROVE",
  "reason_code": null
}
```

- `decision` allowed values: `APPROVE | REJECT | REVIEW`
- Response:

```json
{
  "tx_id": "TXN-001",
  "status": "approved",
  "reason_code": null,
  "trace_id": "TRACE-ABC123"
}
```

## 4) Transaction Status

- `GET /v1/transactions/{tx_id}`
- Resolves from central ledger first, then queue metadata.

## 5) Queue Inspection

- `GET /v1/transactions/queue`
- Query: `state`, `limit`, `offset`

## 6) Ledger Query

- `GET /v1/transactions`
- Query: `status`, `sender_id`, `receiver_id`, `limit`, `offset`

## 7) Device APIs

- `GET /v1/devices/{device_id}/balance`
- `GET /v1/devices/{device_id}/ledger-sync`
- `GET /v1/devices/{device_id}/local-history`
- `GET /v1/devices`

## Error Semantics

- `400`: invalid callback decision
- `404`: unknown tx/device
- `422`: malformed request payload
- `200`: accepted/processed request
