import os
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from opp.crypto import load_private_key, sign_dict
from opp.protocol import make_message
from opp.service import PaymentService
from opp.store import initialize_user, load_wallet, private_key_path


class PaymentServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"OPP_DATA_DIR": self.temp.name})
        self.env.start()
        initialize_user("alice", 10000)
        initialize_user("bob", 0)
        self.service = PaymentService("bob")

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def make_request(self, tx_id=None, sequence=1, amount=1250):
        now = int(time.time())
        payload = {
            "transaction_id": tx_id or str(uuid.uuid4()),
            "payer": "alice",
            "payee": "bob",
            "amount_paise": amount,
            "currency": "INR",
            "sequence": sequence,
            "issued_at": now,
            "expires_at": now + 3600,
        }
        key = load_private_key(private_key_path("alice"))
        message = make_message("PAYMENT_REQUEST", payload, str(uuid.uuid4()))
        message["signature"] = sign_dict(key, payload)
        return message

    def test_accepts_payment_and_credits_once(self):
        request = self.make_request()
        reply = self.service.process(request)
        self.assertEqual(reply["type"], "PAYMENT_ACK")
        self.assertEqual(load_wallet("bob")["balance_paise"], 1250)

    def test_duplicate_transaction_is_idempotent(self):
        request = self.make_request()
        first = self.service.process(request)
        second = self.service.process(request)
        self.assertEqual(first, second)
        self.assertEqual(load_wallet("bob")["balance_paise"], 1250)

    def test_reused_sequence_is_rejected(self):
        first = self.service.process(self.make_request(sequence=1))
        self.assertEqual(first["type"], "PAYMENT_ACK")
        second = self.service.process(self.make_request(sequence=1))
        self.assertEqual(second["type"], "ERROR")
        self.assertEqual(second["payload"]["code"], "REPLAY")
        self.assertEqual(load_wallet("bob")["balance_paise"], 1250)

    def test_tampered_amount_fails_signature(self):
        request = self.make_request()
        request["payload"]["amount_paise"] = 9000
        reply = self.service.process(request)
        self.assertEqual(reply["type"], "ERROR")
        self.assertEqual(reply["payload"]["code"], "BAD_SIGNATURE")
        self.assertEqual(load_wallet("bob")["balance_paise"], 0)


if __name__ == "__main__":
    unittest.main()
