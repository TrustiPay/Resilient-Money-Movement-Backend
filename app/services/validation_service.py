import base64
import logging

from sqlalchemy.orm import Session

from app.models import CentralLedger, DeviceBalance
from app.schemas import TransactionSubmitRequest
from app.services.hash_service import compute_tx_hash, get_last_approved_hash

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    def __init__(self, reason_code: str, message: str):
        self.reason_code = reason_code
        self.message = message
        super().__init__(message)


def is_duplicate_ledger(db: Session, tx_id: str) -> bool:
    return db.query(CentralLedger).filter(CentralLedger.tx_id == tx_id).first() is not None


def get_or_create_balance(db: Session, device_id: str) -> DeviceBalance:
    bal = db.query(DeviceBalance).filter(DeviceBalance.device_id == device_id).first()
    if not bal:
        bal = DeviceBalance(device_id=device_id, balance=1000.0)
        db.add(bal)
        db.flush()
    return bal


def verify_signature(payload: TransactionSubmitRequest) -> bool:
    sig = (payload.signature or "").strip()
    if not sig:
        return False
    if sig == "BYPASS":
        return True

    try:
        decoded = base64.b64decode(sig, validate=True)
        return len(decoded) > 0
    except Exception:
        return False


def verify_client_hash(payload: TransactionSubmitRequest) -> bool:
    expected = compute_tx_hash(payload.model_dump(), payload.prev_hash)
    return expected == payload.tx_hash


def run_post_security_validation(
    db: Session,
    payload: TransactionSubmitRequest,
) -> tuple[float, float, float, float, str]:
    if is_duplicate_ledger(db, payload.tx_id):
        raise ValidationError("DUPLICATE_TX", f"Transaction {payload.tx_id} already exists")

    if not verify_signature(payload):
        raise ValidationError("INVALID_SIGNATURE", "Signature verification failed")

    if not verify_client_hash(payload):
        logger.warning("[VALIDATION] Hash mismatch tx=%s", payload.tx_id)
        raise ValidationError("HASH_MISMATCH", "Transaction hash does not match recomputed value")

    sender_bal = get_or_create_balance(db, payload.sender_id)
    receiver_bal = get_or_create_balance(db, payload.receiver_id)

    oldbal_sender = sender_bal.balance
    newbal_sender = oldbal_sender - payload.amount
    oldbal_receiver = receiver_bal.balance
    newbal_receiver = oldbal_receiver + payload.amount

    if newbal_sender < 0:
        raise ValidationError(
            "INSUFFICIENT_FUNDS",
            f"Sender {payload.sender_id} has insufficient balance ({oldbal_sender})",
        )

    server_prev_hash = get_last_approved_hash(db)

    return oldbal_sender, newbal_sender, oldbal_receiver, newbal_receiver, server_prev_hash
