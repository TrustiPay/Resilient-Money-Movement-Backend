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
from app.services.fraud_service import run_fraud_detection
from app.services.ledger_service import (
    build_fraud_features,
    record_approved,
    record_rejected,
    record_review,
)
from app.services.security_service import SecurityTransportError, verify_transaction
from app.services.validation_service import ValidationError, is_duplicate_ledger, run_post_security_validation

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mark_completed(item: TransactionQueue, final_status: str, reason_code: str | None = None) -> None:
    item.state = "completed"
    item.final_status = final_status
    item.reason_code = reason_code
    item.next_attempt_at = None
    item.processed_at = _now()


def _mark_retry(item: TransactionQueue, error_message: str) -> None:
    item.attempts += 1
    item.state = "retry_wait"
    item.last_error = error_message
    item.next_attempt_at = _now() + timedelta(
        seconds=settings.QUEUE_RETRY_BACKOFF_SECONDS * max(item.attempts, 1)
    )


def _claim_next_item(db: Session) -> TransactionQueue | None:
    now = _now()
    item = (
        db.query(TransactionQueue)
        .filter(TransactionQueue.state.in_(["queued", "retry_wait"]))
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


def _record_duplicate_completion(db: Session, item: TransactionQueue, reason_code: str = "DUPLICATE_TX") -> None:
    _mark_completed(item, "duplicate", reason_code=reason_code)
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

    if is_duplicate_ledger(db, payload.tx_id):
        _record_duplicate_completion(db, item)
        return

    try:
        security_result = verify_transaction(payload.model_dump())
        item.security_decision = security_result.decision
        item.security_reason = security_result.reason
    except SecurityTransportError as exc:
        logger.warning("[QUEUE] Security transport error tx=%s err=%s", item.tx_id, exc)
        if item.attempts + 1 < item.max_attempts:
            _mark_retry(item, str(exc))
            db.commit()
            return

        item.attempts += 1
        item.security_decision = "REVIEW"
        item.security_reason = "SECURITY_UNAVAILABLE"
        record_review(
            db=db,
            payload=payload,
            reason_code="SECURITY_UNAVAILABLE",
            trace_id=item.trace_id,
        )
        _mark_completed(item, "security_review", reason_code="SECURITY_UNAVAILABLE")
        item.last_error = str(exc)
        db.commit()
        return

    if security_result.decision == "FAIL":
        reason_code = security_result.reason or "SECURITY_FAIL"
        record_rejected(db=db, payload=payload, reason_code=reason_code, trace_id=item.trace_id)
        _mark_completed(item, "rejected", reason_code=reason_code)
        db.commit()
        return

    if security_result.decision == "REVIEW":
        reason_code = security_result.reason or "SECURITY_REVIEW"
        record_review(db=db, payload=payload, reason_code=reason_code, trace_id=item.trace_id)
        _mark_completed(item, "security_review", reason_code=reason_code)
        db.commit()
        return

    passed, additional_reason = run_additional_checks(payload.model_dump())
    if not passed:
        reason_code = additional_reason or "ADDITIONAL_CHECK_FAILED"
        record_rejected(db=db, payload=payload, reason_code=reason_code, trace_id=item.trace_id)
        _mark_completed(item, "rejected", reason_code=reason_code)
        db.commit()
        return

    try:
        (
            oldbal_sender,
            newbal_sender,
            oldbal_receiver,
            newbal_receiver,
            server_prev_hash,
        ) = run_post_security_validation(db, payload)
    except ValidationError as exc:
        if exc.reason_code == "DUPLICATE_TX":
            _record_duplicate_completion(db, item)
            return

        record_rejected(db=db, payload=payload, reason_code=exc.reason_code, trace_id=item.trace_id)
        _mark_completed(item, "rejected", reason_code=exc.reason_code)
        db.commit()
        return

    features = build_fraud_features(
        payload=payload,
        oldbal_sender=oldbal_sender,
        newbal_sender=newbal_sender,
        oldbal_receiver=oldbal_receiver,
        newbal_receiver=newbal_receiver,
    )
    fraud_decision, fraud_reason = run_fraud_detection(features)

    if fraud_decision == "REJECT":
        reason_code = fraud_reason or "FRAUD_REJECT"
        record_rejected(
            db=db,
            payload=payload,
            reason_code=reason_code,
            trace_id=item.trace_id,
            oldbal_sender=oldbal_sender,
            newbal_sender=newbal_sender,
            oldbal_receiver=oldbal_receiver,
            newbal_receiver=newbal_receiver,
        )
        _mark_completed(item, "rejected", reason_code=reason_code)
        db.commit()
        return

    if fraud_decision == "REVIEW":
        reason_code = fraud_reason or "FRAUD_REVIEW"
        record_review(
            db=db,
            payload=payload,
            reason_code=reason_code,
            trace_id=item.trace_id,
            oldbal_sender=oldbal_sender,
            newbal_sender=newbal_sender,
            oldbal_receiver=oldbal_receiver,
            newbal_receiver=newbal_receiver,
        )
        _mark_completed(item, "security_review", reason_code=reason_code)
        db.commit()
        return

    record_approved(
        db=db,
        payload=payload,
        trace_id=item.trace_id,
        oldbal_sender=oldbal_sender,
        newbal_sender=newbal_sender,
        oldbal_receiver=oldbal_receiver,
        newbal_receiver=newbal_receiver,
        server_prev_hash=server_prev_hash,
    )
    _mark_completed(item, "approved")
    db.commit()


def process_next_queue_item() -> bool:
    db = SessionLocal()
    try:
        item = _claim_next_item(db)
        if not item:
            return False

        logger.info("[QUEUE] processing tx=%s queue_id=%s", item.tx_id, item.queue_id)
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
