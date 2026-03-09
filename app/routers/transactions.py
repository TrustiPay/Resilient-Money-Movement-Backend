from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CentralLedger, TransactionQueue
from app.schemas import (
    FraudCallbackRequest,
    FraudCallbackResponse,
    FullLedgerResponse,
    HashChainVerifyResponse,
    LedgerEntryResponse,
    OfflineSyncResponse,
    QueueItemResponse,
    QueueListResponse,
    TransactionEnqueueResponse,
    TransactionStatusResponse,
    TransactionSubmitRequest,
)
from app.services.fraud_callback_service import apply_fraud_callback
from app.services.hash_service import get_last_approved_hash
from app.services.queue_service import enqueue_offline_batch, enqueue_transaction

router = APIRouter(prefix="/v1/transactions", tags=["Transactions"])


@router.post(
    "/online",
    response_model=TransactionEnqueueResponse,
    summary="Enqueue an online transaction",
    description=(
        "Accepts a mobile transaction payload and enqueues it for asynchronous processing. "
        "The final status must be polled from GET /v1/transactions/{tx_id}."
    ),
)
def enqueue_online_transaction(
    payload: TransactionSubmitRequest,
    db: Session = Depends(get_db),
):
    return enqueue_transaction(db, payload, source_type="online")


@router.post(
    "/offline-sync",
    response_model=OfflineSyncResponse,
    summary="Enqueue offline pending transactions in batch",
    description=(
        "Accepts an array of offline transactions and enqueues each item. "
        "Returns per-item enqueue outcomes with queued/duplicate statuses."
    ),
)
def offline_sync(
    payloads: List[TransactionSubmitRequest] = Body(...),
    db: Session = Depends(get_db),
):
    if not payloads:
        raise HTTPException(status_code=422, detail="offline-sync payload must contain at least one transaction")
    return enqueue_offline_batch(db, payloads)


@router.post(
    "/submit",
    response_model=TransactionEnqueueResponse,
    deprecated=True,
    summary="Deprecated alias for /v1/transactions/online",
)
def submit_transaction_compat(
    payload: TransactionSubmitRequest,
    db: Session = Depends(get_db),
):
    return enqueue_transaction(db, payload, source_type="online")


@router.post(
    "/fraud-callback",
    response_model=FraudCallbackResponse,
    summary="Receive final fraud decision for a transaction",
    description=(
        "This endpoint is called by the external fraud component after asynchronous analysis. "
        "It finalizes the transaction in central ledger and updates offline device history when applicable."
    ),
)
def fraud_callback(
    payload: FraudCallbackRequest,
    db: Session = Depends(get_db),
):
    return apply_fraud_callback(
        db=db,
        tx_id=payload.tx_id,
        decision=payload.decision,
        reason_code=payload.reason_code,
    )


@router.get(
    "/chain/verify",
    response_model=HashChainVerifyResponse,
    summary="Verify approved transaction hash chain",
)
def verify_hash_chain(db: Session = Depends(get_db)):
    approved = (
        db.query(CentralLedger)
        .filter(CentralLedger.status == "approved")
        .order_by(CentralLedger.ledger_index)
        .all()
    )

    if not approved:
        return HashChainVerifyResponse(
            valid=True,
            checked=0,
            message="No approved transactions in chain.",
        )

    expected_prev = "0" * 64
    for index, tx in enumerate(approved):
        if tx.prev_hash != expected_prev:
            return HashChainVerifyResponse(
                valid=False,
                checked=index,
                broken_at_tx=tx.tx_id,
                message=(
                    f"Chain broken at tx_id={tx.tx_id}: expected prev_hash={expected_prev[:16]}... "
                    f"got={(tx.prev_hash or 'NULL')[:16]}..."
                ),
            )
        expected_prev = tx.tx_hash

    return HashChainVerifyResponse(
        valid=True,
        checked=len(approved),
        message=f"Hash chain intact across {len(approved)} approved transactions.",
    )


@router.get(
    "/queue",
    response_model=QueueListResponse,
    summary="Inspect queue items",
)
def get_queue(
    state: Optional[str] = Query(None, description="Filter by queue state"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(TransactionQueue)
    if state:
        query = query.filter(TransactionQueue.state == state)

    total = query.count()
    rows = query.order_by(TransactionQueue.queue_id.desc()).offset(offset).limit(limit).all()

    return QueueListResponse(
        total=total,
        items=[QueueItemResponse.model_validate(row) for row in rows],
    )


@router.get(
    "",
    response_model=FullLedgerResponse,
    summary="Get full central ledger",
)
def get_full_ledger(
    status: Optional[str] = Query(None, description="Filter by status"),
    sender_id: Optional[str] = Query(None, description="Filter by sender device ID"),
    receiver_id: Optional[str] = Query(None, description="Filter by receiver device ID"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(CentralLedger)
    if status:
        query = query.filter(CentralLedger.status == status)
    if sender_id:
        query = query.filter(CentralLedger.sender_id == sender_id)
    if receiver_id:
        query = query.filter(CentralLedger.receiver_id == receiver_id)

    total = query.count()
    rows = query.order_by(CentralLedger.ledger_index).offset(offset).limit(limit).all()

    return FullLedgerResponse(
        total=total,
        transactions=[LedgerEntryResponse.model_validate(row) for row in rows],
    )


@router.get(
    "/{tx_id}",
    response_model=TransactionStatusResponse,
    summary="Get transaction status",
    description=(
        "Returns current status by checking settled ledger first, then queue state. "
        "Statuses: queued, processing, retry_balance, fraud_detection_pending, security_review, approved, rejected, duplicate."
    ),
)
def get_transaction_status(tx_id: str, db: Session = Depends(get_db)):
    tx = db.query(CentralLedger).filter(CentralLedger.tx_id == tx_id).first()
    if tx:
        return TransactionStatusResponse(
            tx_id=tx.tx_id,
            status=tx.status,
            reason_code=tx.reason_code,
            trace_id=tx.trace_id,
        )

    queued = (
        db.query(TransactionQueue)
        .filter(TransactionQueue.tx_id == tx_id)
        .order_by(TransactionQueue.queue_id.desc())
        .first()
    )

    if not queued:
        raise HTTPException(status_code=404, detail=f"Transaction {tx_id} not found")

    if queued.state == "processing":
        status = "processing"
    elif queued.state == "retry_balance":
        status = "retry_balance"
    elif queued.state in {"queued", "retry_wait"}:
        status = "queued"
    elif queued.state == "completed":
        status = queued.final_status or "queued"
    else:
        status = queued.state

    return TransactionStatusResponse(
        tx_id=tx_id,
        status=status,
        reason_code=queued.reason_code or queued.security_reason,
        trace_id=queued.trace_id,
    )


@router.get(
    "/chain/last-approved-hash",
    summary="Get last approved hash (debug)",
    include_in_schema=False,
)
def get_last_approved_chain_hash(db: Session = Depends(get_db)):
    return {"last_approved_hash": get_last_approved_hash(db)}
