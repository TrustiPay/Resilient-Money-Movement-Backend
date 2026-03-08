import logging

from sqlalchemy.orm import Session

from app.models import CentralLedger
from app.schemas import FraudFeatureVector, TransactionSubmitRequest
from app.services.hash_service import compute_tx_hash
from app.services.validation_service import get_or_create_balance

logger = logging.getLogger(__name__)


def build_fraud_features(
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


def record_rejected(
    db: Session,
    payload: TransactionSubmitRequest,
    reason_code: str,
    trace_id: str,
    oldbal_sender: float = 0.0,
    newbal_sender: float = 0.0,
    oldbal_receiver: float = 0.0,
    newbal_receiver: float = 0.0,
) -> CentralLedger:
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
    return entry


def record_review(
    db: Session,
    payload: TransactionSubmitRequest,
    reason_code: str,
    trace_id: str,
    oldbal_sender: float = 0.0,
    newbal_sender: float = 0.0,
    oldbal_receiver: float = 0.0,
    newbal_receiver: float = 0.0,
) -> CentralLedger:
    review_hash = compute_tx_hash(payload.model_dump(), "")
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
        status="security_review",
        reason_code=reason_code,
        trace_id=trace_id,
    )
    db.add(entry)
    return entry


def record_approved(
    db: Session,
    payload: TransactionSubmitRequest,
    trace_id: str,
    oldbal_sender: float,
    newbal_sender: float,
    oldbal_receiver: float,
    newbal_receiver: float,
    server_prev_hash: str,
) -> CentralLedger:
    approved_hash = compute_tx_hash(payload.model_dump(), server_prev_hash)
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
        tx_hash=approved_hash,
        signature=payload.signature,
        status="approved",
        reason_code=None,
        trace_id=trace_id,
    )
    db.add(entry)

    sender_bal = get_or_create_balance(db, payload.sender_id)
    receiver_bal = get_or_create_balance(db, payload.receiver_id)
    sender_bal.balance = newbal_sender
    receiver_bal.balance = newbal_receiver

    logger.info("[SETTLEMENT] approved tx=%s hash=%s", payload.tx_id, approved_hash[:16])
    return entry
