# Offline Payment Protocol (OPP/1.0)
## Computer Networks Mini Project Report

**Project type:** Application-layer protocol design and TCP socket demonstration  
**Implementation language:** Python 3  
**Transport:** TCP over a local IP network  
**Security primitive:** Ed25519 digital signatures  
**Important:** All balances and payments in this project are simulated classroom data. This is not a regulated payment product.

## 1. Abstract

This project proposes OPP/1.0, a small application-layer protocol that lets two nearby devices exchange a simulated payment request without internet connectivity. The devices communicate over a local Wi-Fi/hotspot network using TCP. Messages are UTF-8 JSON objects framed with a four-byte length prefix. The payer signs payment fields using an Ed25519 private key; the receiver verifies the signature, checks the recipient and amount, applies a transaction-ID/replay check, stores the receipt and updates the receiver's simulated balance. A signed acknowledgment is returned to the payer. This project demonstrates common Computer Networks concepts such as the TCP/IP stack, application-layer message design, byte-stream framing, client/server sockets, reliability, protocol versioning, and error handling.

## 2. Problem statement

Payment applications usually contact a remote service to validate and record transactions. When internet access is unavailable, two nearby users may still need to exchange a small record of value. The project explores how a local network can carry a payment request and signed receipt while disconnected from the internet. The central technical problem is to exchange well-formed messages, authenticate their origin, handle duplicates, and record an uncertain transaction safely.

## 3. Objectives

1. Design a versioned custom application-layer protocol called OPP/1.0.
2. Implement sender/client and receiver/server programs using TCP sockets.
3. Define message framing, common envelope, required fields, acknowledgment and error responses.
4. Use digital signatures to detect altered payment fields and authenticate demo identities.
5. Track local balances, pending transactions, unique IDs and receiver-side replay markers.
6. Test the normal payment path and important error/retry cases.
7. Document limitations and the reconciliation process a real offline payment architecture would need.

## 4. Scope and assumptions

- Both devices must be on the same local Wi-Fi/hotspot or another IP network; neither needs internet access for the demonstration.
- Each device already has a wallet and trusted copy of the other party's public key.
- The demo uses integer paise for INR amounts and a configurable, classroom-only per-payment limit.
- The implementation provides signed message integrity and identity checks, but does not encrypt the message body.
- This is a simulation. It does not issue actual money, connect to UPI/banks, or prevent every form of double-spending.

## 5. Background and protocol choice

The TCP/IP model provides several layers. TCP is suitable for this demonstration because it offers a reliable, ordered byte stream while a connection is active. Since TCP is a byte stream rather than a message protocol, OPP adds a four-byte length prefix before each JSON message. The application layer defines what each message means and which checks the endpoints must perform.

The implementation uses Ed25519 signatures to validate signed payment payloads. Ed25519 is specified in RFC 8032. Deterministic encoding matters whenever structured data is signed; this project defines a stable JSON canonicalization rule. A binary protocol could instead choose deterministic CBOR as specified in RFC 8949.

## 6. System architecture

### Main modules

| Module | Responsibility |
|---|---|
| `opp/cli.py` | Commands to create a wallet, show balances, listen and pay |
| `opp/protocol.py` | Protocol envelope, canonical JSON and length-prefixed TCP framing |
| `opp/crypto.py` | Ed25519 private/public keys, signing and signature verification |
| `opp/store.py` | Wallet JSON files and atomic file replacement |
| `opp/service.py` | Receiver validation, replay protection, receipt creation and balance update |
| `tests/` | Tests for framing, valid payment, tampering, duplicate requests and sequence replay |

### Network stack

```text
Application layer : OPP/1.0 PAYMENT_REQUEST / PAYMENT_ACK / ERROR
Encoding/framing  : UTF-8 JSON + 4-byte big-endian length
Transport layer   : TCP
Network layer     : IP local address
Link layer        : Wi-Fi / personal hotspot
Physical medium   : radio or local network hardware
```

## 7. Protocol specification summary

Every OPP/1.0 frame contains a four-byte unsigned length in network byte order, followed by a UTF-8 JSON object. Frames larger than 65,536 bytes or with invalid lengths are rejected.

The common envelope has `protocol`, `version`, `type`, `message_id`, and `payload` fields. Signed messages additionally contain a Base64-encoded `signature` over canonicalized payload JSON.

### Message types

- **PAYMENT_REQUEST:** transaction ID, payer, payee, amount in paise, currency, payer sequence, issued-at timestamp, expiry timestamp, and payer signature.
- **PAYMENT_ACK:** transaction ID, status, payer, receiver, amount, currency, accepted-at timestamp, and receiver signature.
- **ERROR:** error code, human-readable reason, transaction ID, receiver ID, timestamp, and receiver signature.

See [`PROTOCOL.md`](PROTOCOL.md) for the full normative specification and validation rules.

## 8. Working algorithm

### Sender (Alice)

1. Read Alice's local wallet and verify enough available balance exists.
2. Open a TCP connection to Bob's local IP address and port.
3. Create a unique transaction ID and the next sequence number.
4. Build the payment payload using an integer amount in paise, then sign it.
5. Reserve funds by deducting the amount from Alice's available balance and saving a `PENDING` record.
6. Send the framed request and wait for one response.
7. Verify Bob's signature and transaction ID. Mark the transfer `ACCEPTED` for a valid acknowledgment; restore the funds only for a verified signed rejection. Leave the record pending when the network result is uncertain.

### Receiver (Bob)

1. Accept the TCP connection and read one complete length-prefixed frame.
2. Parse the JSON envelope and verify protocol/version/type.
3. Validate payload fields, receiver identity, amount, currency and expiry.
4. Verify Alice's Ed25519 signature using Alice's previously trusted public key.
5. Reject an already-used payer sequence or conflicting transaction ID. For a duplicate of the same accepted transaction, return the previously saved receipt without crediting the balance a second time.
6. Prepare a signed acknowledgment, add the amount to Bob's balance, and save the balance, replay marker and receipt atomically in Bob's wallet file.
7. Send the signed receipt to Alice.

## 9. State handling

```text
CREATED --> PENDING --> ACCEPTED
                    \-> REJECTED (signed rejection only)
```

A timeout is not automatically a rejection: Bob might have committed the payment but Alice may not have received the acknowledgment. Therefore Alice's wallet keeps the funds reserved and the state pending if the final outcome cannot be authenticated. The starter project does not yet implement a reconciliation/status-query command, so this limitation must be stated in a project demonstration.

## 10. Testing and results

The included automated tests verify:

- A correctly framed message is received intact.
- Unsupported protocol versions are rejected.
- A valid signed payment credits the receiver wallet.
- Retrying the exact same transaction returns the same receipt without double-crediting the receiver.
- Reusing a payer sequence with a different transaction is rejected at that receiver.
- Changing a signed amount after creation fails signature verification.

Run the tests with:

```bash
python -m unittest discover -s tests -v
```

The end-to-end demonstration can be run with the `init`, `listen`, `pay`, and `balance` commands documented in the root README.

## 11. Security analysis and limitations

### Covered by the classroom prototype

- Signature verification detects post-signing changes to the payment payload.
- Unique transaction IDs and receiver-side sequence records prevent simple replay at the same receiver.
- A repeated identical transaction returns a saved receipt instead of crediting the receiver twice.
- Funds are reserved before the sender transmits the payment request.
- A signed acknowledgment gives the sender evidence that the receiver accepted that transaction.

### Not solved by this prototype

- A user could copy an old wallet file and try to spend the same value on two disconnected devices.
- Different offline receivers cannot compare their local histories until reconciliation.
- Wall-clock timestamps can be changed and are not a trustworthy anti-fraud counter.
- A plain local filesystem does not protect keys from a compromised device.
- Public-key files are trusted through manual exchange; there is no certificate authority.
- Messages are signed but not encrypted, so local-network observers may read payment metadata.
- JSON file persistence is suitable for a small demo, not a concurrent financial ledger.

A real deployment would require a carefully designed risk model, hardware-backed keys or another strong control on offline value, identity/key lifecycle management, transaction limits, encrypted channels where appropriate, secure storage, a centralized reconciliation and dispute process, and legal/regulatory review. Offline-payment research highlights double-spending and trusted hardware as central concerns; see the references below.

## 12. Future enhancements

1. Add a central reconciliation server that checks signed transactions when internet access returns.
2. Add query/status and retry commands for pending payments.
3. Add an authenticated certificate or enrolment mechanism for public-key exchange.
4. Add QR, NFC or Bluetooth transport adapters while preserving the same OPP message schema.
5. Use a transactional local database instead of JSON files.
6. Add message encryption/TLS where the operating environment supports it, and clearly manage peer authentication.
7. Add Wireshark packet captures, latency measurements, packet-size measurements and screenshots to the final presentation.

## 13. Conclusion

OPP/1.0 demonstrates how an application-layer protocol can exchange a payment-like message over a local TCP/IP network without internet access. It combines explicit framing, versioned messages, signed payloads, local transaction state, acknowledgment and duplicate handling. The prototype is suitable for a Computer Networks demonstration because it makes both network design and reliability concerns visible. It must remain a simulation: preventing all double-spends across disconnected devices is a broader security and systems problem, not something a custom TCP message alone can solve.

## 14. References

1. IETF RFC 8032, *Edwards-Curve Digital Signature Algorithm (EdDSA)*: https://www.rfc-editor.org/rfc/rfc8032.html
2. IETF RFC 8949, *Concise Binary Object Representation (CBOR)*, including deterministic encoding considerations: https://www.rfc-editor.org/rfc/rfc8949.html
3. Federal Reserve, *A Robust Risk Framework for Offline Payments* (December 2025): https://www.federalreserve.gov/econres/feds/a-robust-risk-framework-for-offline-payments.htm
4. Federal Reserve, *Offline Payments: Implications for Reliability and Resiliency in Digital Payment Systems* (2024): https://www.federalreserve.gov/econres/notes/feds-notes/offline-payments-implications-for-reliability-and-resiliency-in-digital-payment-systems-20240816.html
5. DOLE research proof of concept, *Secure offline P2P payments via trusted hardware*: https://github.com/dominikkipfer/DOLE
