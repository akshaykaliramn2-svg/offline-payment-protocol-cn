"""Command-line interface for the OPP offline payment demo."""
from __future__ import annotations

import argparse
import socket
import time
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .crypto import SignatureError, load_private_key, load_public_key, sign_dict, verify_dict
from .protocol import make_message, recv_frame, send_frame
from .service import PaymentService, MAX_PAYMENT_PAISE, MAX_TTL_SECONDS
from .store import (
    initialize_user,
    load_wallet,
    private_key_path,
    public_key_path,
    save_wallet,
    user_path,
)


def money_to_paise(value: str) -> int:
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("Amount must be a number such as 12.50") from exc
    if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
        raise argparse.ArgumentTypeError("Amount must be positive and have at most two decimal places")
    paise = amount * 100
    if paise != paise.to_integral_value():
        raise argparse.ArgumentTypeError("Amount must have at most two decimal places")
    return int(paise)


def format_money(paise: int) -> str:
    return f"₹{paise // 100}.{paise % 100:02d}"


def balance_to_paise(value: str) -> int:
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("Balance must be a number such as 100.00") from exc
    if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
        raise argparse.ArgumentTypeError("Balance must be zero or positive with at most two decimal places")
    paise = amount * 100
    if paise != paise.to_integral_value():
        raise argparse.ArgumentTypeError("Balance must have at most two decimal places")
    return int(paise)


def cmd_init(args: argparse.Namespace) -> int:
    balance = balance_to_paise(args.balance)
    initialize_user(args.user, balance)
    print(f"Created demo wallet '{args.user}' with balance {format_money(balance)}")
    print(f"Private key (keep secret): {private_key_path(args.user)}")
    print(f"Public key (may be shared): {public_key_path(args.user)}")
    return 0


def cmd_balance(args: argparse.Namespace) -> int:
    wallet = load_wallet(args.user)
    print(f"User: {wallet['user_id']}")
    print(f"Available balance: {format_money(wallet['balance_paise'])}")
    pending = sum(1 for item in wallet["pending"].values() if item.get("state") == "PENDING")
    print(f"Transactions awaiting a confirmed response: {pending}")
    return 0


def cmd_listen(args: argparse.Namespace) -> int:
    import socketserver

    service = PaymentService(args.user)

    class Handler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            # Use the same framed protocol as the sending client; close after one request/reply.
            try:
                request = recv_frame(self.request)
                reply = service.process(request)
                send_frame(self.request, reply)
                print(f"Handled {request.get('type')} from {request.get('payload', {}).get('payer', 'unknown')}: {reply.get('type')}")
            except Exception as exc:
                print(f"Dropped malformed/failed connection: {exc}")

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    with Server((args.host, args.port), Handler) as server:
        print(f"OPP/1.0 receiver '{args.user}' listening on {args.host}:{args.port}")
        print("No internet connection is needed; sender and receiver must share a local network.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nReceiver stopped.")
    return 0


def cmd_pay(args: argparse.Namespace) -> int:
    amount = money_to_paise(args.amount)
    if amount > MAX_PAYMENT_PAISE:
        raise ValueError(f"Demo limit is {format_money(MAX_PAYMENT_PAISE)} per payment")
    if args.payer == args.payee:
        raise ValueError("Payer and payee must be different")

    # Connect first so a failed TCP connection cannot reserve/debit the sender's balance.
    with socket.create_connection((args.host, args.port), timeout=args.timeout) as sock:
        sock.settimeout(args.timeout)
        wallet = load_wallet(args.payer)
        if wallet["balance_paise"] < amount:
            raise ValueError("Insufficient available balance")

        now = int(time.time())
        tx_id = str(uuid.uuid4())
        sequence = wallet["next_sequence"]
        payload: dict[str, Any] = {
            "transaction_id": tx_id,
            "payer": args.payer,
            "payee": args.payee,
            "amount_paise": amount,
            "currency": "INR",
            "sequence": sequence,
            "issued_at": now,
            "expires_at": now + MAX_TTL_SECONDS,
        }
        payer_private_key = load_private_key(private_key_path(args.payer))
        request = make_message("PAYMENT_REQUEST", payload, str(uuid.uuid4()))
        request["signature"] = sign_dict(payer_private_key, payload)

        # Reserve by deducting before sending; ambiguous network failure leaves a pending transaction.
        wallet["balance_paise"] -= amount
        wallet["next_sequence"] += 1
        wallet["pending"][tx_id] = {
            "payload": payload,
            "state": "PENDING",
            "created_at": now,
        }
        save_wallet(wallet)

        try:
            send_frame(sock, request)
            reply = recv_frame(sock)
            reply_payload = reply.get("payload")
            if not isinstance(reply_payload, dict) or not isinstance(reply.get("signature"), str):
                raise SignatureError("Receiver response has no signed payload")
            receiver_public_key = load_public_key(public_key_path(args.payee))
            verify_dict(receiver_public_key, reply_payload, reply["signature"])
            if reply_payload.get("transaction_id") != tx_id:
                raise SignatureError("Receiver response transaction ID does not match")

            wallet = load_wallet(args.payer)
            record = wallet["pending"].get(tx_id)
            if not record:
                raise ValueError("Pending transaction record disappeared")
            if reply.get("type") == "PAYMENT_ACK" and reply_payload.get("status") == "ACCEPTED":
                record["state"] = "ACCEPTED"
                record["receipt"] = reply
                save_wallet(wallet)
                print("PAYMENT ACCEPTED")
                print(f"Transaction ID: {tx_id}")
                print(f"Amount: {format_money(amount)}")
                print(f"Receiver: {args.payee}")
                print(f"New local balance: {format_money(wallet['balance_paise'])}")
                return 0
            if reply.get("type") == "ERROR":
                # Only a cryptographically verified rejection permits a refund.
                wallet["balance_paise"] += amount
                record["state"] = "REJECTED"
                record["error"] = reply_payload
                save_wallet(wallet)
                print(f"PAYMENT REJECTED: {reply_payload.get('code', 'ERROR')} — {reply_payload.get('message', '')}")
                print(f"Balance restored to {format_money(wallet['balance_paise'])}")
                return 2
            raise SignatureError("Unexpected signed response type")
        except (OSError, TimeoutError, ConnectionError, SignatureError, ValueError) as exc:
            # Do not refund on an uncertain outcome: the receiver may have committed but its reply was lost.
            current = load_wallet(args.payer)
            print(f"STATUS UNKNOWN; amount remains reserved: {format_money(amount)}")
            print(f"Transaction ID: {tx_id}")
            print(f"Reason: {exc}")
            print("Reconnect and retry reconciliation manually; do not create a duplicate payment.")
            return 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="opp", description="OPP/1.0 offline payment protocol classroom demo")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create a local demo wallet and Ed25519 key pair")
    init_parser.add_argument("user", help="user ID, e.g. alice")
    init_parser.add_argument("--balance", default="0", help="starting demo balance in rupees, e.g. 100.00")
    init_parser.set_defaults(func=cmd_init)

    balance_parser = subparsers.add_parser("balance", help="show local wallet balance")
    balance_parser.add_argument("user")
    balance_parser.set_defaults(func=cmd_balance)

    listen_parser = subparsers.add_parser("listen", help="listen for payments addressed to a user")
    listen_parser.add_argument("user")
    listen_parser.add_argument("--host", default="0.0.0.0")
    listen_parser.add_argument("--port", type=int, default=9050)
    listen_parser.set_defaults(func=cmd_listen)

    pay_parser = subparsers.add_parser("pay", help="send a signed offline payment over a local TCP network")
    pay_parser.add_argument("payer")
    pay_parser.add_argument("payee")
    pay_parser.add_argument("amount", help="amount in rupees, e.g. 12.50")
    pay_parser.add_argument("--host", default="127.0.0.1", help="receiver IP address")
    pay_parser.add_argument("--port", type=int, default=9050)
    pay_parser.add_argument("--timeout", type=float, default=8.0)
    pay_parser.set_defaults(func=cmd_pay)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except (OSError, ValueError, FileExistsError) as exc:
        parser.exit(1, f"error: {exc}\n")
