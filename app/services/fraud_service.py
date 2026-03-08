from app.schemas import FraudFeatureVector
from typing import Literal
import logging

logger = logging.getLogger(__name__)

FraudDecision = Literal["APPROVE", "REJECT", "REVIEW"]


def run_fraud_detection(features: FraudFeatureVector) -> tuple[FraudDecision, str]:
    """
    Mock fraud detection engine.

    Returns (decision, reason_code).

    Rules applied (prototype heuristics):
    ──────────────────────────────────────
    REJECT  → amount > 50,000  (large single transaction)
    REJECT  → newbal_sender < 0  (overdraft — caught earlier but defence-in-depth)
    REVIEW  → amount > 10,000 and network_type == "offline"
    REVIEW  → location is empty / unknown
    APPROVE → all other cases
    """

    amount      = features.amount
    network     = features.network_type.lower()
    new_bal_s   = features.newbal_sender
    location    = (features.location or "").strip()

    # ── Hard REJECT rules ──────────────────────────────
    if amount > 50_000:
        logger.info(f"[FRAUD] REJECT tx={features.tx_id} reason=AMOUNT_EXCEEDS_LIMIT")
        return "REJECT", "AMOUNT_EXCEEDS_LIMIT"

    if new_bal_s < 0:
        logger.info(f"[FRAUD] REJECT tx={features.tx_id} reason=INSUFFICIENT_FUNDS")
        return "REJECT", "INSUFFICIENT_FUNDS"

    # ── REVIEW rules ───────────────────────────────────
    if amount > 10_000 and network == "offline":
        logger.info(f"[FRAUD] REVIEW tx={features.tx_id} reason=HIGH_VALUE_OFFLINE")
        return "REVIEW", "HIGH_VALUE_OFFLINE"

    if not location or location.lower() in ("unknown", "none", ""):
        logger.info(f"[FRAUD] REVIEW tx={features.tx_id} reason=MISSING_LOCATION")
        return "REVIEW", "MISSING_LOCATION"

    # ── Default APPROVE ────────────────────────────────
    logger.info(f"[FRAUD] APPROVE tx={features.tx_id}")
    return "APPROVE", None
