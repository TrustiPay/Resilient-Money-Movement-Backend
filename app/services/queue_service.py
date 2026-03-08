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

ACTIVE_QUEUE_STATES = {"queued", "processing", "retry_wait"}


def new_trace_id() -> str:
    return f"TRACE-{uuid.uuid4().hex[:12].upper()}"


def is_tx_in_ledger(db: Session, tx_id: str) -> bool:
    return db.query(CentralLedger).filter(CentralLedger.tx_id == tx_id).first() is not None


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
    if is_tx_in_ledger(db, payload.tx_id) or is_tx_in_active_queue(db, payload.tx_id):
        return TransactionEnqueueResponse(tx_id=payload.tx_id, status="duplicate", trace_id="")

    trace_id = new_trace_id()
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
