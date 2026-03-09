import json
import uuid
from typing import Iterable

from sqlalchemy.orm import Session

from app.config import settings
from app.models import CentralLedger, TransactionQueue
from app.schemas import (
    OfflineSyncItemResponse,
    OfflineSyncResponse,
    TransactionEnqueueResponse,
    TransactionSubmitRequest,
)

ACTIVE_QUEUE_STATES = {"queued", "processing", "retry_wait", "retry_balance"}


def new_trace_id() -> str:
    return f"TRACE-{uuid.uuid4().hex[:12].upper()}"


def get_ledger_tx(db: Session, tx_id: str) -> CentralLedger | None:
    return db.query(CentralLedger).filter(CentralLedger.tx_id == tx_id).first()


def is_tx_in_active_queue(db: Session, tx_id: str) -> bool:
    return (
        db.query(TransactionQueue)
        .filter(
            TransactionQueue.tx_id == tx_id,
            TransactionQueue.state.in_(ACTIVE_QUEUE_STATES),
        )
        .first()
        is not None
    )


def enqueue_transaction(
    db: Session,
    payload: TransactionSubmitRequest,
    source_type: str,
) -> TransactionEnqueueResponse:
    existing = get_ledger_tx(db, payload.tx_id)
    if existing:
        # Online submissions always require a fresh tx_id.
        if source_type == "online":
            return TransactionEnqueueResponse(tx_id=payload.tx_id, status="duplicate", trace_id="")
        # Offline can retry only insufficient-funds re-syncs.
        if not (existing.status == "rejected" and existing.reason_code == "INSUFFICIENT_FUNDS"):
            return TransactionEnqueueResponse(tx_id=payload.tx_id, status="duplicate", trace_id="")

    if is_tx_in_active_queue(db, payload.tx_id):
        return TransactionEnqueueResponse(tx_id=payload.tx_id, status="duplicate", trace_id="")

    trace_id = new_trace_id()
    if source_type == "online":
        ledger_entry = CentralLedger(
            tx_id=payload.tx_id,
            sender_id=payload.sender_id,
            receiver_id=payload.receiver_id,
            amount=payload.amount,
            currency="LKR",
            timestamp=payload.timestamp,
            transaction_type=payload.transaction_type,
            device_type=payload.device_type,
            network_type=payload.network_type,
            phone_number=payload.phone_number,
            location=payload.location,
            oldbal_sender=0.0,
            newbal_sender=0.0,
            oldbal_receiver=0.0,
            newbal_receiver=0.0,
            prev_hash=None,
            tx_hash=payload.tx_hash,
            signature=payload.signature,
            status="fraud_detection_pending",
            reason_code=None,
            trace_id=trace_id,
        )
        db.add(ledger_entry)

    queue_item = TransactionQueue(
        tx_id=payload.tx_id,
        source_type=source_type,
        payload_json=json.dumps(payload.model_dump(), sort_keys=True),
        state="queued",
        attempts=0,
        max_attempts=settings.QUEUE_MAX_SECURITY_RETRIES,
        trace_id=trace_id,
    )
    db.add(queue_item)
    db.commit()

    return TransactionEnqueueResponse(tx_id=payload.tx_id, status="queued", trace_id=trace_id)


def enqueue_offline_batch(
    db: Session,
    payloads: Iterable[TransactionSubmitRequest],
) -> OfflineSyncResponse:
    items: list[OfflineSyncItemResponse] = []
    queued = 0
    duplicates = 0

    for payload in payloads:
        result = enqueue_transaction(db, payload, source_type="offline_sync")
        if result.status == "queued":
            queued += 1
        else:
            duplicates += 1
        items.append(
            OfflineSyncItemResponse(
                tx_id=result.tx_id,
                status=result.status,
                trace_id=result.trace_id or None,
            )
        )

    return OfflineSyncResponse(
        total=len(items),
        queued=queued,
        duplicates=duplicates,
        items=items,
    )
