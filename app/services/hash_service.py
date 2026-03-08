import hashlib
import json


def compute_tx_hash(payload: dict, prev_hash: str) -> str:
    """
    Compute SHA-256 transaction hash deterministically.
    Uses a canonical subset of fields + prev_hash to produce the hash.
    """
    canonical = {
        "tx_id":            payload.get("tx_id"),
        "sender_id":        payload.get("sender_id"),
        "receiver_id":      payload.get("receiver_id"),
        "amount":           payload.get("amount"),
        "timestamp":        payload.get("timestamp"),
        "transaction_type": payload.get("transaction_type"),
        "prev_hash":        prev_hash,
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_tx_hash(payload: dict, prev_hash: str, submitted_hash: str) -> bool:
    """Recompute hash and compare with client-submitted hash."""
    expected = compute_tx_hash(payload, prev_hash)
    return expected == submitted_hash


def get_last_approved_hash(db) -> str:
    """Retrieve the tx_hash of the last approved transaction in the chain."""
    from app.models import CentralLedger
    last = (
        db.query(CentralLedger)
        .filter(CentralLedger.status == "approved")
        .order_by(CentralLedger.ledger_index.desc())
        .first()
    )
    if last:
        return last.tx_hash
    # Genesis hash — chain anchor
    return "0" * 64
