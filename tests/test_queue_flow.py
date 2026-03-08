import os
import unittest
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite:///./test_trustipay.db"
os.environ["ENABLE_QUEUE_WORKER"] = "false"
os.environ["SECURITY_ENDPOINT_URL"] = "http://security.local/verify"

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import DeviceBalance
from app.routers.transactions import get_transaction_status, verify_hash_chain
from app.schemas import TransactionSubmitRequest
from app.services.hash_service import compute_tx_hash
from app.services.queue_processor_service import process_next_queue_item
from app.services.queue_service import enqueue_offline_batch, enqueue_transaction
from app.services.security_service import SecurityResult, SecurityTransportError


class QueueFlowTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        settings.ENABLE_QUEUE_WORKER = False
        settings.QUEUE_MAX_SECURITY_RETRIES = 2
        settings.QUEUE_RETRY_BACKOFF_SECONDS = 0.01
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def _payload(self, tx_id: str, sender: str, receiver: str, amount: float = 100.0) -> TransactionSubmitRequest:
        prev_hash = "0" * 64
        payload = {
            "tx_id": tx_id,
            "sender_id": sender,
            "receiver_id": receiver,
            "timestamp": "2026-03-08T10:30:00Z",
            "amount": amount,
            "transaction_type": "QR",
            "device_type": "Pixel 8",
            "network_type": "offline",
            "phone_number": "+94770000000",
            "location": "Western Province",
            "prev_hash": prev_hash,
            "tx_hash": "",
            "signature": "BYPASS",
        }
        payload["tx_hash"] = compute_tx_hash(payload, prev_hash)
        return TransactionSubmitRequest.model_validate(payload)

    def test_online_enqueue_returns_queued(self):
        payload = self._payload("TX-ONLINE-1", "ALICE", "BOB")
        result = enqueue_transaction(self.db, payload, source_type="online")
        self.assertEqual(result.status, "queued")

        status = get_transaction_status(payload.tx_id, db=self.db)
        self.assertEqual(status.status, "queued")

    def test_offline_sync_handles_mixed_duplicates(self):
        payload_1 = self._payload("TX-BATCH-1", "ALICE", "BOB")
        payload_2 = self._payload("TX-BATCH-2", "ALICE", "CHARLIE")

        enqueue_transaction(self.db, payload_1, source_type="online")
        batch_result = enqueue_offline_batch(self.db, [payload_1, payload_2])

        self.assertEqual(batch_result.total, 2)
        self.assertEqual(batch_result.queued, 1)
        self.assertEqual(batch_result.duplicates, 1)

    def test_processor_pass_path_approves_and_updates_balances(self):
        payload = self._payload("TX-APPROVE-1", "ALICE", "BOB")
        enqueue_transaction(self.db, payload, source_type="online")

        with patch(
            "app.services.queue_processor_service.verify_transaction",
            return_value=SecurityResult(decision="PASS", reason=None),
        ), patch(
            "app.services.queue_processor_service.run_additional_checks",
            return_value=(True, None),
        ), patch(
            "app.services.queue_processor_service.run_fraud_detection",
            return_value=("APPROVE", None),
        ):
            self.assertTrue(process_next_queue_item())

        self.db.expire_all()
        status = get_transaction_status(payload.tx_id, db=self.db)
        self.assertEqual(status.status, "approved")

        sender = self.db.query(DeviceBalance).filter(DeviceBalance.device_id == "ALICE").first()
        receiver = self.db.query(DeviceBalance).filter(DeviceBalance.device_id == "BOB").first()
        self.assertIsNotNone(sender)
        self.assertIsNotNone(receiver)
        self.assertAlmostEqual(sender.balance, 900.0)
        self.assertAlmostEqual(receiver.balance, 1100.0)

    def test_processor_security_fail_rejects_without_balance_updates(self):
        payload = self._payload("TX-REJECT-1", "DEV1", "DEV2")
        enqueue_transaction(self.db, payload, source_type="online")

        with patch(
            "app.services.queue_processor_service.verify_transaction",
            return_value=SecurityResult(decision="FAIL", reason="SECURITY_RULE_BLOCK"),
        ):
            self.assertTrue(process_next_queue_item())

        self.db.expire_all()
        status = get_transaction_status(payload.tx_id, db=self.db)
        self.assertEqual(status.status, "rejected")
        self.assertEqual(status.reason_code, "SECURITY_RULE_BLOCK")

        sender = self.db.query(DeviceBalance).filter(DeviceBalance.device_id == "DEV1").first()
        receiver = self.db.query(DeviceBalance).filter(DeviceBalance.device_id == "DEV2").first()
        self.assertIsNone(sender)
        self.assertIsNone(receiver)

    def test_security_transport_retries_then_review(self):
        payload = self._payload("TX-REVIEW-1", "S1", "S2")
        enqueue_transaction(self.db, payload, source_type="online")

        with patch(
            "app.services.queue_processor_service.verify_transaction",
            side_effect=SecurityTransportError("timeout"),
        ):
            first = process_next_queue_item()
            second = process_next_queue_item()

        self.assertTrue(first)
        self.assertTrue(second)

        self.db.expire_all()
        status = get_transaction_status(payload.tx_id, db=self.db)
        self.assertEqual(status.status, "security_review")

    def test_hash_chain_only_counts_approved_transactions(self):
        approved_payload = self._payload("TX-CHAIN-1", "A1", "B1")
        rejected_payload = self._payload("TX-CHAIN-2", "A2", "B2")

        enqueue_transaction(self.db, approved_payload, source_type="online")
        enqueue_transaction(self.db, rejected_payload, source_type="online")

        with patch(
            "app.services.queue_processor_service.verify_transaction",
            side_effect=[
                SecurityResult(decision="PASS", reason=None),
                SecurityResult(decision="FAIL", reason="SECURITY_FAIL"),
            ],
        ), patch(
            "app.services.queue_processor_service.run_additional_checks",
            return_value=(True, None),
        ), patch(
            "app.services.queue_processor_service.run_fraud_detection",
            return_value=("APPROVE", None),
        ):
            process_next_queue_item()
            process_next_queue_item()

        self.db.expire_all()
        chain = verify_hash_chain(db=self.db)
        self.assertTrue(chain.valid)
        self.assertEqual(chain.checked, 1)


if __name__ == "__main__":
    unittest.main()
