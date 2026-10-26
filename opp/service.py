"""Receiver-side OPP message validation and payment acceptance."""
from __future__ import annotations

import hashlib
import threading
import time
import uuid
from typing import Any

from .crypto import SignatureError, load_private_key, load_public_key, sign_dict, verify_dict
from .protocol import make_message, canonical_json_bytes
from .store import load_wallet, private_key_path, public_key_path, save_wallet

# Classroom-demo policy limits, not limits imposed by any bank or payment network.
MAX_PAYMENT_PAISE = 100_000  # ₹1,000 per payment in this demo.
MAX_TTL_SECONDS = 7 * 24 * 60 * 60
CLOCK_SKEW_SECONDS = 5 * 60


class PaymentRejected(ValueError):
    def __init__(self, code: str, message: str, transaction_id: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.transaction_id = transaction_id


class PaymentService:
    def __init__(self, receiver_id: str) -> None:
        self.receiver_id = receiver_id
        self._lock = threading.Lock()

    def _signed_reply(self, reply_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        private_key = load_private_key(private_key_path(self.receiver_id))
        message = make_message(reply_type, payload, str(uuid.uuid4()))
        message["signature"] = sign_dict(private_key, payload)
        return message

    def error_reply(self, exc: PaymentRejected) -> dict[str, Any]:
        return self._signed_reply("ERROR", {
            "code": exc.code,
            "message": str(exc),
            "transaction_id": exc.transaction_id,
            "receiver": self.receiver_id,
            "timestamp": int(time.time()),
        })

    def process(self, request: dict[str, Any]) -> dict[str, Any]:
        tx_id = ""
        try:
            with self._lock:
                return self._process_locked(request)
        except PaymentRejected as exc:
            return self.error_reply(exc)
        except (FileNotFoundError, SignatureError, KeyError, TypeError, ValueError) as exc:
            return self.error_reply(PaymentRejected("INVALID_REQUEST", str(exc), tx_id))

    def _process_locked(self, request: dict[str, Any]) -> dict[str, Any]:
        if request.get("protocol") != "OPP" or request.get("version") != "1.0":
            raise PaymentRejected("BAD_VERSION", "Unsupported protocol or version")
        if request.get("type") != "PAYMENT_REQUEST":
            raise PaymentRejected("BAD_TYPE", "Expected PAYMENT_REQUEST")
        payload = request.get("payload")
        signature = request.get("signature")
        if not isinstance(payload, dict) or not isinstance(signature, str):
            raise PaymentRejected("BAD_FORMAT", "Missing payload or signature")

        required = {"transaction_id", "payer", "payee", "amount_paise", "currency", "sequence", "issued_at", "expires_at"}
        if not required.issubset(payload):
            raise PaymentRejected("BAD_FORMAT", "Payment payload is missing required fields", str(payload.get("transaction_id", "")))

        tx_id = payload["transaction_id"]
        payer = payload["payer"]
        payee = payload["payee"]
        amount = payload["amount_paise"]
        sequence = payload["sequence"]
        now = int(time.time())

        if not isinstance(tx_id, str) or not tx_id or len(tx_id) > 80:
            raise PaymentRejected("BAD_FORMAT", "Invalid transaction ID")
        if not isinstance(payer, str) or not payer or not isinstance(payee, str):
            raise PaymentRejected("BAD_FORMAT", "Invalid payer or payee ID", tx_id)
        if payee != self.receiver_id:
            raise PaymentRejected("WRONG_RECIPIENT", "Payment is addressed to another user", tx_id)
        if payer == payee:
            raise PaymentRejected("SELF_PAYMENT", "Payer and payee must be different", tx_id)
        # bool is a subclass of int in Python, so reject it explicitly.
        if isinstance(amount, bool) or not isinstance(amount, int) or not 1 <= amount <= MAX_PAYMENT_PAISE:
            raise PaymentRejected("BAD_AMOUNT", "Amount must be a positive integer number of paise within the demo limit", tx_id)
        if payload["currency"] != "INR":
            raise PaymentRejected("BAD_CURRENCY", "Only INR is supported by this demo", tx_id)
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise PaymentRejected("BAD_SEQUENCE", "Sequence must be a positive integer", tx_id)
        issued_at = payload["issued_at"]
        expires_at = payload["expires_at"]
        if not isinstance(issued_at, int) or not isinstance(expires_at, int):
            raise PaymentRejected("BAD_TIME", "Invalid transaction timestamps", tx_id)
        if issued_at > now + CLOCK_SKEW_SECONDS or expires_at < now or expires_at <= issued_at:
            raise PaymentRejected("EXPIRED", "Payment is expired or has an invalid timestamp", tx_id)
        if expires_at - issued_at > MAX_TTL_SECONDS:
            raise PaymentRejected("BAD_TTL", "Payment validity period exceeds the demo limit", tx_id)

        payer_key = load_public_key(public_key_path(payer))
        try:
            verify_dict(payer_key, payload, signature)
        except SignatureError as exc:
            raise PaymentRejected("BAD_SIGNATURE", "Payer signature is not valid", tx_id) from exc

        wallet = load_wallet(self.receiver_id)
        payload_hash = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        old_record = wallet["received_transactions"].get(tx_id)
        if old_record:
            if old_record.get("payload_hash") != payload_hash:
                raise PaymentRejected("TX_ID_CONFLICT", "Transaction ID was reused with different contents", tx_id)
            # Idempotent retry: resend the exact same signed receipt without crediting again.
            return old_record["reply"]

        sequence_key = f"{payer}:{sequence}"
        if sequence_key in wallet["seen_sequences"]:
            raise PaymentRejected("REPLAY", "This payer sequence number has already been used at this receiver", tx_id)

        receipt_payload = {
            "transaction_id": tx_id,
            "status": "ACCEPTED",
            "payer": payer,
            "receiver": self.receiver_id,
            "amount_paise": amount,
            "currency": "INR",
            "accepted_at": now,
        }
        reply = self._signed_reply("PAYMENT_ACK", receipt_payload)

        # Balance, replay data and receipt are committed together in one atomic wallet-file replace.
        wallet["balance_paise"] += amount
        wallet["seen_sequences"].append(sequence_key)
        wallet["received_transactions"][tx_id] = {
            "payload_hash": payload_hash,
            "reply": reply,
        }
        save_wallet(wallet)
        return reply
