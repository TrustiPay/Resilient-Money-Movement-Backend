import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import TransactionQueue
from app.schemas import FraudCallbackResponse, TransactionSubmitRequest
from app.services.device_history_service import upsert_device_history
from app.services.ledger_service import approve_from_payload, get_ledger_tx, record_rejected, record_review


def _load_payload_from_queue(db: Session, tx_id: str) -> tuple[TransactionSubmitRequest, str, str | None]:
    queue_item = (
        db.query(TransactionQueue)
        .filter(TransactionQueue.tx_id == tx_id)
        .order_by(TransactionQueue.queue_id.desc())
        .first()
    )
    if not queue_item:
        raise HTTPException(status_code=404, detail=f"Transaction {tx_id} not found in queue")

    payload = TransactionSubmitRequest.model_validate(json.loads(queue_item.payload_json))
    return payload, queue_item.source_type, queue_item.trace_id


def apply_fraud_callback(
    db: Session,
    tx_id: str,
    decision: str,
    reason_code: str | None = None,
) -> FraudCallbackResponse:
    normalized = decision.strip().upper()
    approved_values = {"CONFIRMED", "APPROVE", "APPROVED"}
    rejected_values = {"REJECT", "REJECTED"}
    review_values = {"REVIEW", "SECURITY_REVIEW"}
    if normalized not in approved_values | rejected_values | review_values:
        raise HTTPException(
            status_code=400,
            detail="decision must be CONFIRMED/APPROVE/APPROVED/REJECT/REJECTED/REVIEW/SECURITY_REVIEW",
        )

    payload, source_type, trace_id = _load_payload_from_queue(db, tx_id)
    trace_id = trace_id or ""

    existing = get_ledger_tx(db, tx_id)
    if existing and existing.status in {"approved", "rejected", "security_review"}:
        return FraudCallbackResponse(
            tx_id=tx_id,
            status=existing.status,
            reason_code=existing.reason_code,
            trace_id=existing.trace_id,
        )

    if normalized in approved_values:
        try:
            approved = approve_from_payload(db=db, payload=payload, trace_id=trace_id)
        except ValueError:
            record_rejected(
                db=db,
                payload=payload,
                reason_code="INSUFFICIENT_FUNDS",
                trace_id=trace_id,
            )
            db.commit()
            return FraudCallbackResponse(
                tx_id=tx_id,
                status="rejected",
                reason_code="INSUFFICIENT_FUNDS",
                trace_id=trace_id,
            )

        if source_type == "offline_sync":
            upsert_device_history(
                db=db,
                payload=payload,
                source_type=source_type,
                status="approved",
                trace_id=trace_id,
                reason_code=None,
            )
        db.commit()
        return FraudCallbackResponse(
            tx_id=tx_id,
            status=approved.status,
            reason_code=None,
            trace_id=approved.trace_id,
        )

    if normalized in rejected_values:
        reason = reason_code or "FRAUD_REJECT"
        rejected = record_rejected(db=db, payload=payload, reason_code=reason, trace_id=trace_id)
        if source_type == "offline_sync":
            upsert_device_history(
                db=db,
                payload=payload,
                source_type=source_type,
                status="rejected",
                trace_id=trace_id,
                reason_code=reason,
            )
        db.commit()
        return FraudCallbackResponse(
            tx_id=tx_id,
            status=rejected.status,
            reason_code=reason,
            trace_id=rejected.trace_id,
        )

    reason = reason_code or "FRAUD_REVIEW"
    review = record_review(db=db, payload=payload, reason_code=reason, trace_id=trace_id)
    if source_type == "offline_sync":
        upsert_device_history(
            db=db,
            payload=payload,
            source_type=source_type,
            status="security_review",
            trace_id=trace_id,
            reason_code=reason,
        )
    db.commit()
    return FraudCallbackResponse(
        tx_id=tx_id,
        status=review.status,
        reason_code=reason,
        trace_id=review.trace_id,
    )
