from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import CentralLedger
from app.schemas import (
    TransactionSubmitRequest,
    TransactionSubmitResponse,
    TransactionStatusResponse,
    LedgerEntryResponse,
    FullLedgerResponse,
    HashChainVerifyResponse,
)
from app.services.ledger_service import settle_transaction
from app.services.hash_service import compute_tx_hash

router = APIRouter(prefix="/v1/transactions", tags=["Transactions"])


@router.post(
    "/submit",
    response_model=TransactionSubmitResponse,
    summary="Submit a transaction for settlement",
    description="""
Accepts a mobile transaction payload and runs the full validation + settlement pipeline:

1. Schema validation  
2. Duplicate check  
3. Hash recomputation  
4. Signature verification  
5. Balance computation  
6. Fraud detection  
7. Ledger update (atomic)

Returns the initial status: **approved**, **rejected**, or **fraud_review**.
""",
)
def submit_transaction(
    payload: TransactionSubmitRequest,
    db: Session = Depends(get_db),
):
    return settle_transaction(db, payload)


@router.get(
    "/{tx_id}",
    response_model=TransactionStatusResponse,
    summary="Get transaction status by ID",
    description="Poll the settlement status of a previously submitted transaction.",
)
def get_transaction_status(tx_id: str, db: Session = Depends(get_db)):
    tx = db.query(CentralLedger).filter(CentralLedger.tx_id == tx_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail=f"Transaction {tx_id} not found")
    return TransactionStatusResponse(
        tx_id=tx.tx_id,
        status=tx.status,
        reason_code=tx.reason_code,
        trace_id=tx.trace_id,
    )


@router.get(
    "",
    response_model=FullLedgerResponse,
    summary="Get full central ledger",
    description="""
Returns all transactions in the central ledger including approved, rejected, 
fraud_review, and duplicate entries.

Supports optional filters:
- **status**: filter by status (approved / rejected / fraud_review)
- **sender_id**: filter by sender device
- **receiver_id**: filter by receiver device
- **limit** / **offset**: pagination

Designed for integration with external fraud detection and behaviour pattern analysis systems.
""",
)
def get_full_ledger(
    status:      Optional[str] = Query(None, description="Filter by status"),
    sender_id:   Optional[str] = Query(None, description="Filter by sender device ID"),
    receiver_id: Optional[str] = Query(None, description="Filter by receiver device ID"),
    limit:       int           = Query(100, ge=1, le=1000, description="Page size"),
    offset:      int           = Query(0, ge=0, description="Page offset"),
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
    rows  = query.order_by(CentralLedger.ledger_index).offset(offset).limit(limit).all()

    return FullLedgerResponse(
        total=total,
        transactions=[LedgerEntryResponse.model_validate(r) for r in rows],
    )


@router.get(
    "/chain/verify",
    response_model=HashChainVerifyResponse,
    summary="Verify the tamper-evident hash chain",
    description="""
Walks through all **approved** transactions in ledger index order and verifies 
that each `prev_hash` correctly references the previous approved transaction's `tx_hash`.

Returns whether the chain is intact and identifies the first broken link if not.
""",
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
            valid=True, checked=0, message="No approved transactions in chain."
        )

    genesis = "0" * 64
    expected_prev = genesis

    for tx in approved:
        if tx.prev_hash != expected_prev:
            return HashChainVerifyResponse(
                valid=False,
                checked=approved.index(tx),
                broken_at_tx=tx.tx_id,
                message=f"Chain broken at tx_id={tx.tx_id}: "
                        f"expected prev_hash={expected_prev[:16]}… "
                        f"got={tx.prev_hash[:16] if tx.prev_hash else 'NULL'}…",
            )
        expected_prev = tx.tx_hash

    return HashChainVerifyResponse(
        valid=True,
        checked=len(approved),
        message=f"Hash chain intact across {len(approved)} approved transactions.",
    )
