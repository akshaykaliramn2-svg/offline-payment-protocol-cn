# OPP/1.0 Architecture and Working

## Component view

```text
+---------------------+                  +---------------------+
| Alice CLI / Wallet  |                  | Bob CLI / Wallet    |
|---------------------|                  |---------------------|
| Balance + sequence  |                  | TCP receiver        |
| Payment builder     |                  | Protocol parser     |
| Ed25519 signer      |                  | Ed25519 verifier    |
| Pending transaction |                  | Replay/ID checks    |
| TCP client          |                  | Atomic local update |
+----------+----------+                  +----------+----------+
           |                                        ^
           |         OPP/1.0 over TCP/IP            |
           +--------------------------------------->+
```

## Execution flow

1. **Enrolment/setup (before offline use):** each user gets a wallet and Ed25519 key pair. The demo's public keys are manually copied to the other user's `data/keys/` folder. Private keys stay local.
2. **Payment creation:** payer checks its local balance, creates a UUID transaction ID, increments a sequence number, writes the amount as integer paise and signs the canonical payload.
3. **Reservation:** payer deducts the amount from its available balance and saves a `PENDING` record before sending. This reduces accidental duplicate spending from repeat commands.
4. **Transport:** client connects to receiver's local IP and TCP port, then sends a 4-byte length prefix followed by a JSON message.
5. **Verification:** receiver checks protocol version, recipient, amount, currency, timestamp, key signature and replay identifiers.
6. **Local commit:** receiver credits their simulated balance and saves both the receipt and replay markers in one atomic JSON-file replacement.
7. **Acknowledgment:** receiver returns a signed accepted receipt. Payer verifies the signature and moves the pending record to `ACCEPTED`.
8. **Uncertain result:** if the network fails after the payment may have been sent, payer does not automatically refund. It keeps a pending record so the same transaction can be retried safely.
9. **Reconciliation (future extension):** when internet returns, a central service checks all signed records and identifies globally conflicting sequence numbers / overspending.

## Why TCP?

TCP provides an ordered, reliable byte stream while a connection is alive. It does **not** preserve application message boundaries, so OPP adds a length prefix. TCP does not provide payment authentication, ledger correctness or double-spend prevention by itself; those are application concerns.

## Offline does not mean disconnected from every network

This demonstration is offline from the internet but still uses a local IP network: two devices connect to the same Wi-Fi/hotspot and communicate by private/local IP address. If no local network exists, a QR/NFC/Bluetooth adapter could exchange the signed payload, but that transport is not implemented in this repository.
