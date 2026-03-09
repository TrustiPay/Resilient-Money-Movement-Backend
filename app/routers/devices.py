from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CentralLedger, DeviceBalance, DeviceTransactionHistory
from app.schemas import (
    DeviceBalanceResponse,
    DeviceHistoryEntryResponse,
    DeviceHistorySyncResponse,
    DeviceStateSyncResponse,
    LedgerSyncResponse,
    LedgerEntryResponse,
)

router = APIRouter(prefix="/v1/devices", tags=["Devices"])


@router.get(
    "/{device_id}/balance",
    response_model=DeviceBalanceResponse,
    summary="Get device balance",
    description="Returns the current settled balance for the given device. "
                "New devices are initialised with a 1,000 LKR seed balance.",
)
def get_device_balance(device_id: str, db: Session = Depends(get_db)):
    bal = db.query(DeviceBalance).filter(DeviceBalance.device_id == device_id).first()
    if not bal:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")
    return DeviceBalanceResponse(
        device_id=bal.device_id,
        balance=bal.balance,
        currency="LKR",
        updated_at=str(bal.updated_at) if bal.updated_at else None,
    )


@router.get(
    "/{device_id}/ledger-sync",
    response_model=LedgerSyncResponse,
    summary="Ledger sync for a device",
    description="""
Returns all ledger entries where the device is either the **sender** or **receiver**.

Used by mobile clients to reconcile their local offline ledger against the 
settled central ledger after reconnecting to the network.
""",
)
def ledger_sync(device_id: str, db: Session = Depends(get_db)):
    rows = (
        db.query(CentralLedger)
        .filter(
            (CentralLedger.sender_id == device_id) |
            (CentralLedger.receiver_id == device_id)
        )
        .order_by(CentralLedger.ledger_index)
        .all()
    )

    return LedgerSyncResponse(
        device_id=device_id,
        total=len(rows),
        transactions=[LedgerEntryResponse.model_validate(r) for r in rows],
    )


@router.get(
    "/{device_id}/local-history",
    response_model=DeviceHistorySyncResponse,
    summary="Get local transaction history mirror for a device",
    description=(
        "Returns entries from device_transaction_history for offline synchronization tracking. "
        "This mirrors statuses pushed after fraud callbacks."
    ),
)
def local_history_sync(device_id: str, db: Session = Depends(get_db)):
    rows = (
        db.query(DeviceTransactionHistory)
        .filter(
            (DeviceTransactionHistory.sender_id == device_id) |
            (DeviceTransactionHistory.receiver_id == device_id)
        )
        .order_by(DeviceTransactionHistory.history_id)
        .all()
    )
    return DeviceHistorySyncResponse(
        device_id=device_id,
        total=len(rows),
        transactions=[DeviceHistoryEntryResponse.model_validate(r) for r in rows],
    )


@router.get(
    "/{device_id}/sync-state",
    response_model=DeviceStateSyncResponse,
    summary="Sync local transaction statuses and balance from central ledger",
    description=(
        "Returns central ledger transactions and current settled balance for the device. "
        "Mobile app can use this as the single source of truth to update local status and wallet balance."
    ),
)
def sync_state(device_id: str, db: Session = Depends(get_db)):
    bal = db.query(DeviceBalance).filter(DeviceBalance.device_id == device_id).first()
    if not bal:
        bal = DeviceBalance(device_id=device_id, balance=1000.0)
        db.add(bal)
        db.commit()
        db.refresh(bal)

    rows = (
        db.query(CentralLedger)
        .filter(
            (CentralLedger.sender_id == device_id) |
            (CentralLedger.receiver_id == device_id)
        )
        .order_by(CentralLedger.ledger_index)
        .all()
    )

    return DeviceStateSyncResponse(
        device_id=device_id,
        balance=bal.balance,
        currency="LKR",
        updated_at=str(bal.updated_at) if bal.updated_at else None,
        total=len(rows),
        transactions=[LedgerEntryResponse.model_validate(r) for r in rows],
    )


@router.get(
    "",
    response_model=list[DeviceBalanceResponse],
    summary="List all registered devices and balances",
    description="Returns all devices currently registered in the ledger with their balances.",
)
def list_devices(db: Session = Depends(get_db)):
    devices = db.query(DeviceBalance).all()
    return [
        DeviceBalanceResponse(
            device_id=d.device_id,
            balance=d.balance,
            currency="LKR",
            updated_at=str(d.updated_at) if d.updated_at else None,
        )
        for d in devices
    ]
