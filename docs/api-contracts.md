# API Contracts

Base URL examples assume `http://localhost:8000`.

## Shared Transaction Payload

```json
{
  "tx_id": "string",
  "sender_id": "string",
  "receiver_id": "string",
  "timestamp": "string",
  "amount": 0,
  "transaction_type": "string",
  "device_type": "string",
  "network_type": "string",
  "phone_number": "string",
  "location": "string",
  "prev_hash": "string",
  "tx_hash": "string",
  "signature": "string"
}
```

## Status Values

Public status values returned by APIs:

- `queued`
- `processing`
- `security_review`
- `approved`
- `rejected`
- `duplicate`

## 1) Enqueue Online Transaction

- Method: `POST`
- Path: `/v1/transactions/online`

### Response

```json
{
  "tx_id": "TXN-001",
  "status": "queued",
  "trace_id": "TRACE-ABC123"
}
```

`status` can be `queued` or `duplicate`.

## 2) Offline Batch Sync

- Method: `POST`
- Path: `/v1/transactions/offline-sync`
- Body: JSON array of transaction payload objects

### Response

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

## 3) Backward-Compatible Submit Alias

- Method: `POST`
- Path: `/v1/transactions/submit`
- Behavior: same as `/v1/transactions/online`
- Note: deprecated; keep for compatibility only.

## 4) Get Transaction Status

- Method: `GET`
- Path: `/v1/transactions/{tx_id}`

Resolution order:

1. If `tx_id` exists in `central_ledger`, return settled status.
2. Else resolve from `transaction_queue` state/final status.

### Response

```json
{
  "tx_id": "TXN-001",
  "status": "processing",
  "reason_code": null,
  "trace_id": "TRACE-ABC123"
}
```

## 5) Central Ledger Query

- Method: `GET`
- Path: `/v1/transactions`
- Query params:
  - `status`
  - `sender_id`
  - `receiver_id`
  - `limit` (default 100)
  - `offset` (default 0)

## 6) Queue Inspection

- Method: `GET`
- Path: `/v1/transactions/queue`
- Query params:
  - `state`
  - `limit`
  - `offset`

Returns operational queue metadata (`attempts`, `next_attempt_at`, `final_status`, etc.).

## 7) Hash Chain Verification

- Method: `GET`
- Path: `/v1/transactions/chain/verify`

Verifies approved-only chain continuity.

## 8) Device Endpoints

- `GET /v1/devices/{device_id}/balance`
- `GET /v1/devices/{device_id}/ledger-sync`
- `GET /v1/devices`

## Error Semantics

- `404`: transaction or device not found
- `422`: invalid request payload (including empty offline sync array)
- `200`: enqueue accepted (including duplicate detection outcome)

## Eventual Consistency Contract

- Enqueue endpoints do not guarantee immediate settlement.
- Clients must poll `GET /v1/transactions/{tx_id}` for final status.
