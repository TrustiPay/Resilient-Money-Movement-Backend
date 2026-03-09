from sqlalchemy.orm import Session

from app.models import DeviceTransactionHistory
from app.schemas import TransactionSubmitRequest


def upsert_device_history(
    db: Session,
    payload: TransactionSubmitRequest,
    source_type: str,
    status: str,
    trace_id: str | None,
    reason_code: str | None = None,
) -> DeviceTransactionHistory:
    history = (
        db.query(DeviceTransactionHistory)
        .filter(DeviceTransactionHistory.tx_id == payload.tx_id)
        .first()
    )
    if not history:
        history = DeviceTransactionHistory(
            tx_id=payload.tx_id,
            sender_id=payload.sender_id,
            receiver_id=payload.receiver_id,
            amount=payload.amount,
            source_type=source_type,
            status=status,
            reason_code=reason_code,
            trace_id=trace_id,
        )
        db.add(history)
    else:
        history.status = status
        history.reason_code = reason_code
        history.trace_id = trace_id
        history.source_type = source_type

    return history
