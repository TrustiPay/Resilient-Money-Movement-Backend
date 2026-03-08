from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class TransactionSubmitRequest(BaseModel):
    tx_id: str = Field(..., description="Unique transaction ID generated on mobile")
    sender_id: str = Field(..., description="Sender device ID")
    receiver_id: str = Field(..., description="Receiver device ID")
    timestamp: str = Field(..., description="Transaction creation timestamp (ISO 8601)")
    amount: float = Field(..., gt=0, description="Payment amount (must be > 0)")
    transaction_type: str = Field(..., description="QR / Bluetooth / WiFi")
    device_type: str = Field(..., description="Mobile device model")
    network_type: str = Field(..., description="wifi / cellular / offline")
    phone_number: str = Field(..., description="Phone number used")
    location: str = Field(..., description="Province or region")
    prev_hash: str = Field(..., description="Previous local ledger hash")
    tx_hash: str = Field(..., description="Transaction hash computed by mobile")
    signature: str = Field(..., description="Sender cryptographic signature")

    model_config = {
        "json_schema_extra": {
            "example": {
                "tx_id": "TXN-20240601-001",
                "sender_id": "DEV-ALICE-001",
                "receiver_id": "DEV-BOB-002",
                "timestamp": "2024-06-01T10:30:00Z",
                "amount": 150.00,
                "transaction_type": "QR",
                "device_type": "Samsung Galaxy S23",
                "network_type": "offline",
                "phone_number": "+94771234567",
                "location": "Western Province",
                "prev_hash": "0000000000000000000000000000000000000000000000000000000000000000",
                "tx_hash": "abc123def456",
                "signature": "base64-encoded-signature",
            }
        }
    }


class FraudFeatureVector(BaseModel):
    tx_id: str
    sender_id: str
    receiver_id: str
    timestamp: str
    amount: float
    transaction_type: str
    oldbal_sender: float
    newbal_sender: float
    oldbal_receiver: float
    newbal_receiver: float
    device_type: str
    network_type: str
    phone_number: str
    location: str


class TransactionEnqueueResponse(BaseModel):
    tx_id: str
    status: str
    trace_id: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "tx_id": "TXN-20240601-001",
                "status": "queued",
                "trace_id": "TRACE-abc123",
            }
        }
    }


class OfflineSyncItemResponse(BaseModel):
    tx_id: str
    status: str
    trace_id: Optional[str] = None


class OfflineSyncResponse(BaseModel):
    total: int
    queued: int
    duplicates: int
    items: List[OfflineSyncItemResponse]


class TransactionStatusResponse(BaseModel):
    tx_id: str
    status: str
    reason_code: Optional[str] = None
    trace_id: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "tx_id": "TXN-20240601-001",
                "status": "processing",
                "reason_code": None,
                "trace_id": "TRACE-abc123",
            }
        }
    }


class DeviceBalanceResponse(BaseModel):
    device_id: str
    balance: float
    currency: str = "LKR"
    updated_at: Optional[str]


class LedgerEntryResponse(BaseModel):
    ledger_index: int
    tx_id: str
    sender_id: str
    receiver_id: str
    amount: float
    currency: str
    timestamp: str
    transaction_type: Optional[str]
    device_type: Optional[str]
    network_type: Optional[str]
    phone_number: Optional[str]
    location: Optional[str]
    oldbal_sender: float
    newbal_sender: float
    oldbal_receiver: float
    newbal_receiver: float
    prev_hash: Optional[str]
    tx_hash: str
    signature: Optional[str]
    status: str
    reason_code: Optional[str]
    trace_id: Optional[str]

    model_config = {"from_attributes": True}


class LedgerSyncResponse(BaseModel):
    device_id: str
    total: int
    transactions: List[LedgerEntryResponse]


class FullLedgerResponse(BaseModel):
    total: int
    transactions: List[LedgerEntryResponse]


class HashChainVerifyResponse(BaseModel):
    valid: bool
    checked: int
    broken_at_tx: Optional[str] = None
    message: str


class QueueItemResponse(BaseModel):
    queue_id: int
    tx_id: str
    source_type: str
    state: str
    attempts: int
    max_attempts: int
    next_attempt_at: Optional[datetime]
    trace_id: str
    last_error: Optional[str]
    security_decision: Optional[str]
    security_reason: Optional[str]
    final_status: Optional[str]
    reason_code: Optional[str]
    processed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class QueueListResponse(BaseModel):
    total: int
    items: List[QueueItemResponse]
