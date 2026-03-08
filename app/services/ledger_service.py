import uuid
import logging
from sqlalchemy.orm import Session

from app.models import CentralLedger, DeviceBalance
from app.schemas import (
    TransactionSubmitRequest,
    FraudFeatureVector,
    TransactionSubmitResponse,
)
from app.services.validation_service import (
    ValidationError,
    run_validation_pipeline,
    get_or_create_balance,
)
from app.services.fraud_service import run_fraud_detection
from app.services.hash_service import compute_tx_hash

logger = logging.getLogger(__name__)


def _build_fraud_features(
    payload: TransactionSubmitRequest,
    oldbal_sender: float,
    newbal_sender: float,
    oldbal_receiver: float,
    newbal_receiver: float,
) -> FraudFeatureVector:
    return FraudFeatureVector(
        tx_id=payload.tx_id,
        sender_id=payload.sender_id,
        receiver_id=payload.receiver_id,
        timestamp=payload.timestamp,
        amount=payload.amount,
        transaction_type=payload.transaction_type,
        oldbal_sender=oldbal_sender,
        newbal_sender=newbal_sender,
        oldbal_receiver=oldbal_receiver,
        newbal_receiver=newbal_receiver,
        device_type=payload.device_type,
        network_type=payload.network_type,
        phone_number=payload.phone_number,
        location=payload.location,
    )


def settle_transaction(
    db: Session,
    payload: TransactionSubmitRequest,
) -> TransactionSubmitResponse:
    """
    Full settlement pipeline — atomic.
    Returns a TransactionSubmitResponse with final status.
    """
    trace_id = f"TRACE-{uuid.uuid4().hex[:12].upper()}"
    logger.info(f"[SETTLE] Starting settlement trace={trace_id} tx={payload.tx_id}")

    # ── Phase 1: Validation ───────────────────────────────────────────
    try:
        (
            oldbal_sender,
            newbal_sender,
            oldbal_receiver,
            newbal_receiver,
            server_prev_hash,
        ) = run_validation_pipeline(db, payload)
    except ValidationError as ve:
        logger.warning(f"[SETTLE] Validation failed tx={payload.tx_id} reason={ve.reason_code}")
        if ve.reason_code == "DUPLICATE_TX":
            return TransactionSubmitResponse(
                tx_id=payload.tx_id,
                status="duplicate",
                trace_id=trace_id,
            )
        _record_rejected(db, payload, ve.reason_code, trace_id)
        db.commit()
        return TransactionSubmitResponse(
            tx_id=payload.tx_id,
            status="rejected",
            trace_id=trace_id,
        )

    # ── Phase 2: Fraud Detection ──────────────────────────────────────
    features = _build_fraud_features(
        payload, oldbal_sender, newbal_sender, oldbal_receiver, newbal_receiver
    )
    fraud_decision, fraud_reason = run_fraud_detection(features)
    logger.info(f"[SETTLE] Fraud decision={fraud_decision} tx={payload.tx_id}")

    if fraud_decision == "REJECT":
        _record_rejected(db, payload, fraud_reason or "FRAUD_REJECT", trace_id,
                         oldbal_sender, newbal_sender, oldbal_receiver, newbal_receiver)
        db.commit()
        return TransactionSubmitResponse(
            tx_id=payload.tx_id,
            status="rejected",
            trace_id=trace_id,
        )

    if fraud_decision == "REVIEW":
        _record_review(db, payload, fraud_reason or "FRAUD_REVIEW", trace_id,
                       oldbal_sender, newbal_sender, oldbal_receiver, newbal_receiver,
                       server_prev_hash)
        db.commit()
        return TransactionSubmitResponse(
            tx_id=payload.tx_id,
            status="fraud_review",
            trace_id=trace_id,
        )

    # ── Phase 3: Approve & Settle ─────────────────────────────────────
    server_tx_hash = compute_tx_hash(payload.model_dump(), server_prev_hash)

    entry = CentralLedger(
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
        oldbal_sender=oldbal_sender,
        newbal_sender=newbal_sender,
        oldbal_receiver=oldbal_receiver,
        newbal_receiver=newbal_receiver,
        prev_hash=server_prev_hash,
        tx_hash=server_tx_hash,
        signature=payload.signature,
        status="approved",
        reason_code=None,
        trace_id=trace_id,
    )
    db.add(entry)

    # Update balances atomically
    sender_bal   = get_or_create_balance(db, payload.sender_id)
    receiver_bal = get_or_create_balance(db, payload.receiver_id)
    sender_bal.balance   = newbal_sender
    receiver_bal.balance = newbal_receiver

    db.commit()
    logger.info(f"[SETTLE] Approved tx={payload.tx_id} hash={server_tx_hash[:16]}…")

    return TransactionSubmitResponse(
        tx_id=payload.tx_id,
        status="approved",
        trace_id=trace_id,
    )


# ── Private helpers ───────────────────────────────────────────────────────────

def _record_rejected(
    db, payload, reason_code, trace_id,
    oldbal_sender=0.0, newbal_sender=0.0,
    oldbal_receiver=0.0, newbal_receiver=0.0,
):
    rejected_hash = compute_tx_hash(payload.model_dump(), "")
    entry = CentralLedger(
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
        oldbal_sender=oldbal_sender,
        newbal_sender=newbal_sender,
        oldbal_receiver=oldbal_receiver,
        newbal_receiver=newbal_receiver,
        prev_hash=None,
        tx_hash=rejected_hash,
        signature=payload.signature,
        status="rejected",
        reason_code=reason_code,
        trace_id=trace_id,
    )
    db.add(entry)


def _record_review(
    db, payload, reason_code, trace_id,
    oldbal_sender, newbal_sender, oldbal_receiver, newbal_receiver,
    server_prev_hash,
):
    review_hash = compute_tx_hash(payload.model_dump(), server_prev_hash)
    entry = CentralLedger(
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
        oldbal_sender=oldbal_sender,
        newbal_sender=newbal_sender,
        oldbal_receiver=oldbal_receiver,
        newbal_receiver=newbal_receiver,
        prev_hash=None,
        tx_hash=review_hash,
        signature=payload.signature,
        status="fraud_review",
        reason_code=reason_code,
        trace_id=trace_id,
    )
    db.add(entry)
