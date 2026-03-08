from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from sqlalchemy.sql import func
from app.database import Base


class CentralLedger(Base):
    __tablename__ = "central_ledger"

    ledger_index     = Column(Integer, primary_key=True, autoincrement=True)
    tx_id            = Column(String, unique=True, nullable=False, index=True)
    sender_id        = Column(String, nullable=False, index=True)
    receiver_id      = Column(String, nullable=False, index=True)
    amount           = Column(Float, nullable=False)
    currency         = Column(String, default="LKR")
    timestamp        = Column(String, nullable=False)
    transaction_type = Column(String)
    device_type      = Column(String)
    network_type     = Column(String)
    phone_number     = Column(String)
    location         = Column(String)
    oldbal_sender    = Column(Float, default=0.0)
    newbal_sender    = Column(Float, default=0.0)
    oldbal_receiver  = Column(Float, default=0.0)
    newbal_receiver  = Column(Float, default=0.0)
    prev_hash        = Column(String, nullable=True)
    tx_hash          = Column(String, nullable=False)
    signature        = Column(Text)
    status           = Column(String, default="queued")
    reason_code      = Column(String, nullable=True)
    trace_id         = Column(String, nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())


class DeviceBalance(Base):
    __tablename__ = "device_balances"

    device_id  = Column(String, primary_key=True, index=True)
    balance    = Column(Float, default=1000.0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TransactionQueue(Base):
    __tablename__ = "transaction_queue"

    queue_id          = Column(Integer, primary_key=True, autoincrement=True)
    tx_id             = Column(String, nullable=False, index=True)
    source_type       = Column(String, nullable=False)
    payload_json      = Column(Text, nullable=False)
    state             = Column(String, nullable=False, default="queued")
    attempts          = Column(Integer, nullable=False, default=0)
    max_attempts      = Column(Integer, nullable=False, default=3)
    next_attempt_at   = Column(DateTime(timezone=True), nullable=True)
    trace_id          = Column(String, nullable=False, index=True)
    last_error        = Column(Text, nullable=True)
    security_decision = Column(String, nullable=True)
    security_reason   = Column(String, nullable=True)
    final_status      = Column(String, nullable=True, index=True)
    reason_code       = Column(String, nullable=True)
    processed_at      = Column(DateTime(timezone=True), nullable=True)
    created_at        = Column(DateTime(timezone=True), server_default=func.now())
    updated_at        = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
