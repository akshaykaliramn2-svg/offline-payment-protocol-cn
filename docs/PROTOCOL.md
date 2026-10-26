# OPP/1.0 Protocol Specification

## 1. Status and purpose

OPP means **Offline Payment Protocol**. This document defines a small application-layer protocol for an academic Computer Networks demonstration. A payer and payee exchange a signed payment request locally, using TCP/IP over Wi-Fi or a mobile hotspot. Neither device needs internet access during this exchange.

OPP is not a banking standard, and the implementation is not a real-money payment product. Its purpose is to demonstrate protocol design, framing, signatures, local state, acknowledgment, replay handling and the constraints of offline settlement.

## 2. Network placement

| Layer | OPP choice | Purpose |
|---|---|---|
| Application | OPP/1.0 | Payment request, receipt, rejection and validation rules |
| Presentation/encoding | UTF-8 JSON with sorted keys for signatures | Interoperable message representation |
| Session/framing | 4-byte length prefix | Delimits one JSON message on a TCP byte stream |
| Transport | TCP | Reliable, ordered byte stream and connection state |
| Network | IPv4/IPv6 | Local host addressing; no internet route is required |
| Link | Wi-Fi/hotspot Ethernet-like local link | Carries packets between nearby devices |

A future version could use QR, NFC or Bluetooth to transport the same signed application payload. Those are transport adaptations; they do not change the meaning of OPP payment fields.

## 3. Wire format and framing

Each TCP message is:

```text
+-------------------------------+----------------------------+
| Length: unsigned 32-bit value | JSON message: Length bytes |
| network byte order (big-endian)| UTF-8 encoded               |
+-------------------------------+----------------------------+
```

- `Length` excludes the 4-byte length field itself.
- The receiver MUST read exactly four bytes, decode the length, reject lengths of 0 or greater than 65,536 bytes, then read exactly that many bytes.
- TCP does not preserve application message boundaries. The length prefix makes the application messages unambiguous even if a TCP read returns partial data or multiple segments arrive close together.
- The body MUST be a UTF-8 JSON object. Unknown protocol names or versions are rejected.
- JSON used for signatures is canonicalised by UTF-8 encoding JSON with sorted keys, compact separators, Unicode preserved, and NaN/Infinity disallowed.

## 4. Common message envelope

```json
{
  "protocol": "OPP",
  "version": "1.0",
  "type": "PAYMENT_REQUEST",
  "message_id": "unique-message-uuid",
  "payload": { "...": "message-specific fields" },
  "signature": "base64-encoded-Ed25519-signature"
}
```

`signature` is omitted only for unsigned messages, but the current payment and response messages are signed. The Ed25519 signature covers the canonical JSON bytes of `payload`. The signature is not computed over its own `signature` field. Ed25519 signatures authenticate the payload's origin and detect edits; they do not encrypt the message. This demo assumes the public key associated with each user ID was already exchanged and trusted.

## 5. Message types

### 5.1 PAYMENT_REQUEST — payer to payee

Required payload fields:

| Field | Type | Meaning / validation |
|---|---|---|
| `transaction_id` | string | Unique ID for this logical payment; retries reuse it |
| `payer` | string | Sender wallet ID |
| `payee` | string | Intended receiver; must match the listening wallet |
| `amount_paise` | integer | Positive integer in paise; floats are not accepted |
| `currency` | string | `INR` for this demo |
| `sequence` | integer | Monotonically increasing payer-wallet counter |
| `issued_at` | integer | Unix timestamp in seconds |
| `expires_at` | integer | Unix timestamp after which the request is invalid |

Example (illustrative only; the signature is omitted here):

```json
{
  "protocol": "OPP",
  "version": "1.0",
  "type": "PAYMENT_REQUEST",
  "message_id": "f53e...",
  "payload": {
    "transaction_id": "c5e9...",
    "payer": "alice",
    "payee": "bob",
    "amount_paise": 1250,
    "currency": "INR",
    "sequence": 1,
    "issued_at": 1793050000,
    "expires_at": 1793654800
  },
  "signature": "<base64 signature over canonical payload>"
}
```

The program's demo limit is ₹1,000 per payment and a maximum validity interval of seven days. These values are configurable teaching constraints, **not official financial limits**.

### 5.2 PAYMENT_ACK — payee to payer

The receiver signs an acknowledgment only after it has verified the request and persisted the receipt and credited balance locally.

Payload fields: `transaction_id`, `status` (`ACCEPTED`), `payer`, `receiver`, `amount_paise`, `currency`, and `accepted_at`.

The payer MUST verify the receiver's signature and check that `transaction_id` matches the pending payment before marking it accepted.

### 5.3 ERROR — payee to payer

A rejection has a signed payload containing `code`, `message`, `transaction_id`, `receiver`, and `timestamp`. Example codes include `BAD_VERSION`, `BAD_TYPE`, `BAD_FORMAT`, `BAD_AMOUNT`, `BAD_CURRENCY`, `BAD_SEQUENCE`, `BAD_SIGNATURE`, `EXPIRED`, `WRONG_RECIPIENT`, `REPLAY`, and `TX_ID_CONFLICT`.

The payer only restores the reserved amount on a cryptographically verified rejection. A connection timeout or invalid response is an uncertain outcome, not proof of rejection. In that case, the transaction remains pending and the balance remains reserved.

## 6. Rules for accepting a payment

The receiver performs these checks in order:

1. Parse a correctly framed message and require `OPP` version `1.0` and type `PAYMENT_REQUEST`.
2. Check required payload fields, payer/payee IDs, positive integer amount, currency, sequence and timestamp format.
3. Require the payee to be the local receiver, disallow self-payment, and enforce demo-specific payment/expiry limits.
4. Load the previously trusted payer public key and verify the Ed25519 signature over canonical payload bytes.
5. Check the transaction ID. If a matching accepted transaction was already processed, return the saved receipt without crediting twice. If the ID is reused for different data, reject it.
6. Reject a previously seen `payer:sequence` pair at this receiver.
7. Create a signed receipt, credit the local payee wallet, and save the replay marker and receipt via a single atomic wallet-file replacement.
8. Send the signed `PAYMENT_ACK` over the existing TCP connection.

## 7. Sender state machine

```text
CREATED -> PENDING -> ACCEPTED
                  \-> REJECTED (only after verified signed ERROR)
```

The sender checks its local balance and opens TCP before reserving funds. It then deducts/reserves the amount and records the payment as `PENDING` before transmitting the request. A valid signed acknowledgment changes the state to `ACCEPTED`. A verified signed rejection restores the balance and marks the request `REJECTED`. A timeout or broken connection leaves the payment pending because the receiver might have accepted it but the response could have been lost.

## 8. Offline and double-spending limitations

A signature prevents a third party from changing a signed amount without detection, and a transaction ID/sequence protects against straightforward replay at the same receiver. These measures do **not** prove that the payer had not copied an old wallet file and spent the same balance on another disconnected device. Separate offline receivers cannot compare their ledgers until they reconnect. A real system needs stronger trusted hardware or controlled pre-authorised value, strict offline limits, credential management, and reconciliation that identifies conflicting spends and decides who bears the loss.

The example code is a learning model only. It has no certificate authority, hardware-backed key protection, production-grade multi-process database, recovery process, or dispute-management process.

## 9. Reconnection and reconciliation (design extension)

When connectivity returns, each device can upload signed local records to a central reconciliation service. The service should:

- authenticate the device and validate signatures and issuer credentials;
- enforce global uniqueness of transaction IDs and payer sequence numbers;
- compare spending against the issuer-approved offline allocation;
- detect conflicting spend histories and mark them for review rather than silently treating both as final;
- return a signed reconciliation result and record audit events;
- never trust a client-supplied balance as the single source of truth.

This central stage is outside the code included in this starter repository.

## 10. Security and operational requirements

- Never transmit or commit private keys. The public key is not secret, but it must be authenticated during enrolment.
- Do not treat device wall-clock time as a trustworthy anti-fraud counter; time validation in this prototype is educational only.
- Keep TCP listening on a trusted local network. The demo does not encrypt payloads, and signatures provide authenticity/integrity rather than confidentiality.
- Do not reuse or reset wallet files for real value. Do not connect this prototype to any actual account or payment rail.
- Use integer minor currency units; never use binary floating point for money.
