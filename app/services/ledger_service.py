import logging

from sqlalchemy.orm import Session

from app.models import CentralLedger
from app.schemas import FraudFeatureVector, TransactionSubmitRequest
from app.services.hash_service import compute_tx_hash, get_last_approved_hash
from app.services.validation_service import get_or_create_balance

logger = logging.getLogger(__name__)


def get_ledger_tx(db: Session, tx_id: str) -> CentralLedger | None:
    return db.query(CentralLedger).filter(CentralLedger.tx_id == tx_id).first()


def ensure_pending_fraud(
    db: Session,
    payload: TransactionSubmitRequest,
    trace_id: str,
    status: str = "fraud_detection_pending",
) -> CentralLedger:
    entry = get_ledger_tx(db, payload.tx_id)
    if not entry:
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
            oldbal_sender=0.0,
            newbal_sender=0.0,
            oldbal_receiver=0.0,
            newbal_receiver=0.0,
            prev_hash=None,
            tx_hash=payload.tx_hash,
            signature=payload.signature,
            status=status,
            reason_code=None,
            trace_id=trace_id,
        )
        db.add(entry)
    else:
        entry.status = status
        entry.reason_code = None
        entry.trace_id = trace_id
    return entry


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
    entry = get_ledger_tx(db, payload.tx_id)
    if not entry:
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
    else:
        entry.status = "rejected"
        entry.reason_code = reason_code
        entry.trace_id = trace_id
        entry.oldbal_sender = oldbal_sender
        entry.newbal_sender = newbal_sender
        entry.oldbal_receiver = oldbal_receiver
        entry.newbal_receiver = newbal_receiver
        entry.prev_hash = None
        entry.tx_hash = rejected_hash
        entry.signature = payload.signature
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
    entry = get_ledger_tx(db, payload.tx_id)
    if not entry:
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
    else:
        entry.status = "security_review"
        entry.reason_code = reason_code
        entry.trace_id = trace_id
        entry.oldbal_sender = oldbal_sender
        entry.newbal_sender = newbal_sender
        entry.oldbal_receiver = oldbal_receiver
        entry.newbal_receiver = newbal_receiver
        entry.prev_hash = None
        entry.tx_hash = review_hash
        entry.signature = payload.signature
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
    entry = get_ledger_tx(db, payload.tx_id)
    if not entry:
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
    else:
        entry.status = "approved"
        entry.reason_code = None
        entry.trace_id = trace_id
        entry.oldbal_sender = oldbal_sender
        entry.newbal_sender = newbal_sender
        entry.oldbal_receiver = oldbal_receiver
        entry.newbal_receiver = newbal_receiver
        entry.prev_hash = server_prev_hash
        entry.tx_hash = approved_hash
        entry.signature = payload.signature

    sender_bal = get_or_create_balance(db, payload.sender_id)
    receiver_bal = get_or_create_balance(db, payload.receiver_id)
    sender_bal.balance = newbal_sender
    receiver_bal.balance = newbal_receiver

    logger.info("[SETTLEMENT] approved tx=%s hash=%s", payload.tx_id, approved_hash[:16])
    return entry


def approve_from_payload(
    db: Session,
    payload: TransactionSubmitRequest,
    trace_id: str,
) -> CentralLedger:
    sender_bal = get_or_create_balance(db, payload.sender_id)
    receiver_bal = get_or_create_balance(db, payload.receiver_id)

    oldbal_sender = sender_bal.balance
    newbal_sender = oldbal_sender - payload.amount
    oldbal_receiver = receiver_bal.balance
    newbal_receiver = oldbal_receiver + payload.amount

    if newbal_sender < 0:
        raise ValueError("INSUFFICIENT_FUNDS")

    server_prev_hash = get_last_approved_hash(db)
    return record_approved(
        db=db,
        payload=payload,
        trace_id=trace_id,
        oldbal_sender=oldbal_sender,
        newbal_sender=newbal_sender,
        oldbal_receiver=oldbal_receiver,
        newbal_receiver=newbal_receiver,
        server_prev_hash=server_prev_hash,
    )
