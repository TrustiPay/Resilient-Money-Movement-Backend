import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import TransactionQueue
from app.schemas import TransactionSubmitRequest
from app.services.additional_checks_service import run_additional_checks
from app.services.ledger_service import ensure_pending_fraud, record_rejected
from app.services.validation_service import ValidationError, run_post_security_validation

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mark_completed(item: TransactionQueue, final_status: str, reason_code: str | None = None) -> None:
    item.state = "completed"
    item.final_status = final_status
    item.reason_code = reason_code
    item.next_attempt_at = None
    item.processed_at = _now()


def _mark_balance_retry(item: TransactionQueue) -> None:
    item.attempts += 1
    item.state = "retry_balance"
    item.reason_code = "INSUFFICIENT_FUNDS"
    item.next_attempt_at = _now() + timedelta(seconds=settings.QUEUE_POLL_INTERVAL_SECONDS * 5)


def _claim_next_item(db: Session) -> TransactionQueue | None:
    now = _now()
    item = (
        db.query(TransactionQueue)
        .filter(TransactionQueue.state.in_(["queued", "retry_balance"]))
        .filter(
            or_(
                TransactionQueue.next_attempt_at.is_(None),
                TransactionQueue.next_attempt_at <= now,
            )
        )
        .order_by(TransactionQueue.queue_id.asc())
        .first()
    )

    if not item:
        return None

    item.state = "processing"
    item.last_error = None
    db.commit()
    db.refresh(item)
    return item


def _process_online(db: Session, item: TransactionQueue, payload: TransactionSubmitRequest) -> None:
    ensure_pending_fraud(db, payload, trace_id=item.trace_id, status="fraud_detection_pending")
    _mark_completed(item, "fraud_detection_pending")
    db.commit()


def _process_offline(db: Session, item: TransactionQueue, payload: TransactionSubmitRequest) -> None:
    try:
        (
            oldbal_sender,
            newbal_sender,
            oldbal_receiver,
            newbal_receiver,
            _server_prev_hash,
        ) = run_post_security_validation(db, payload)
    except ValidationError as exc:
        # Keep writing rejected state in central ledger; insufficient funds remains retry-eligible.
        record_rejected(db=db, payload=payload, reason_code=exc.reason_code, trace_id=item.trace_id)
        if exc.reason_code == "INSUFFICIENT_FUNDS":
            _mark_balance_retry(item)
            db.commit()
            return
        if exc.reason_code == "DUPLICATE_TX":
            _mark_completed(item, "rejected", reason_code=exc.reason_code)
            db.commit()
            return
        _mark_completed(item, "rejected", reason_code=exc.reason_code)
        db.commit()
        return

    passed, additional_reason = run_additional_checks(payload.model_dump())
    if not passed:
        reason_code = additional_reason or "ADDITIONAL_CHECK_FAILED"
        record_rejected(db=db, payload=payload, reason_code=reason_code, trace_id=item.trace_id)
        _mark_completed(item, "rejected", reason_code=reason_code)
        db.commit()
        return

    pending_row = ensure_pending_fraud(db, payload, trace_id=item.trace_id, status="fraud_detection_pending")
    pending_row.oldbal_sender = oldbal_sender
    pending_row.newbal_sender = newbal_sender
    pending_row.oldbal_receiver = oldbal_receiver
    pending_row.newbal_receiver = newbal_receiver
    _mark_completed(item, "fraud_detection_pending")
    db.commit()


def _process_item(db: Session, item: TransactionQueue) -> None:
    try:
        payload_dict = json.loads(item.payload_json)
        payload = TransactionSubmitRequest.model_validate(payload_dict)
    except Exception as exc:
        logger.exception("[QUEUE] Invalid payload tx=%s", item.tx_id)
        _mark_completed(item, "rejected", reason_code="INVALID_PAYLOAD")
        item.last_error = str(exc)
        db.commit()
        return

    if item.source_type == "online":
        _process_online(db, item, payload)
        return

    _process_offline(db, item, payload)


def process_next_queue_item() -> bool:
    db = SessionLocal()
    try:
        item = _claim_next_item(db)
        if not item:
            return False

        logger.info("[QUEUE] processing tx=%s queue_id=%s source=%s", item.tx_id, item.queue_id, item.source_type)
        _process_item(db, item)
        return True
    except Exception:
        logger.exception("[QUEUE] unexpected processing failure")
        db.rollback()
        return False
    finally:
        db.close()


async def run_queue_worker(stop_event: asyncio.Event) -> None:
    logger.info("[QUEUE] worker started")
    while not stop_event.is_set():
        processed = await asyncio.to_thread(process_next_queue_item)
        if processed:
            await asyncio.sleep(0)
            continue

        await asyncio.sleep(settings.QUEUE_POLL_INTERVAL_SECONDS)

    logger.info("[QUEUE] worker stopped")
