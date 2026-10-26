# OPP/1.0 — Offline Payment Protocol (Computer Networks Project)

OPP is a **classroom prototype** that demonstrates how two devices can exchange a payment message over a local TCP/IP network without internet access. It is deliberately a simulated wallet: balances are test data, not real money.

## Project goals

- Demonstrate an application-layer protocol over TCP.
- Define message framing, message types, fields, and status/error codes.
- Use Ed25519 digital signatures to verify who created a payment and a receipt.
- Show offline-first behaviour, locally stored balances, replay checks, transaction IDs, and idempotent retries.
- Explain what must happen when devices reconnect to a central reconciliation service.

> **Safety and scope:** this code is not suitable for real payments. Ordinary files on a phone/computer can be copied or modified, and disconnected devices cannot know whether another disconnected device has already accepted the same value. A production system needs a trusted secure element or equivalent controls, certified keys, robust atomic storage, device-loss handling, limits, audits, and a reconciliation/dispute process. This demo does not prevent deliberate wallet cloning or all forms of double-spending.

## Requirements

- Python 3.10 or newer
- `cryptography` Python package

## Install

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux:       source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Quick demo on one computer

Open two terminals in this project directory. Run these setup commands once:

```bash
python -m opp init alice --balance 100.00
python -m opp init bob --balance 0.00
```

Terminal 1 — start Bob's receiver:

```bash
python -m opp listen bob --host 127.0.0.1 --port 9050
```

Terminal 2 — send Alice's payment of ₹12.50 to Bob:

```bash
python -m opp pay alice bob 12.50 --host 127.0.0.1 --port 9050
```

Check the balances:

```bash
python -m opp balance alice
python -m opp balance bob
```

Expected result: Alice's simulated balance decreases to ₹87.50, Bob's increases to ₹12.50, and Alice records a signed receipt. Stop the receiver with `Ctrl+C`.

The demo stores local wallet/key files in `data/`. That folder is ignored by Git because it contains private keys and changing local state. **Never commit private keys or wallet data.** If you rerun the quick demo from scratch, delete the demo `data/wallets/` and `data/keys/` files first, or choose a fresh data folder.

## Demo on two computers connected to the same Wi-Fi/hotspot (no internet)

1. Install the project and dependencies on both computers. A local Wi-Fi network or hotspot is enough; internet access is not needed.
2. On Alice's computer, initialise Alice. On Bob's computer, initialise Bob. Keep each computer's private key private.
3. Copy **only** `alice.public.pem` into Bob's `data/keys/` directory, and `bob.public.pem` into Alice's `data/keys/` directory. The keys must be exchanged/trusted before using the demo.
4. Start the receiver on Bob's computer, for example `python -m opp listen bob --host 0.0.0.0 --port 9050`.
5. On Alice's computer, use Bob's local-network IP: `python -m opp pay alice bob 12.50 --host 192.168.x.x --port 9050`.
6. If the operating-system firewall asks, allow the receiver only on the trusted private network. Do not expose the demo port to the public internet.

For separate computers, set `OPP_DATA_DIR` to a folder dedicated to each user's local wallet before running commands. The exact environment-variable command differs by operating system; see `docs/TESTING.md`.

## Project map

```text
offline-payment-protocol-cn/
├── README.md                 # setup and demo instructions
├── requirements.txt          # cryptography dependency
├── .gitignore                # excludes local wallet and key material
├── opp/
│   ├── __main__.py           # python -m opp entry point
│   ├── cli.py                # init, balance, listen and pay commands
│   ├── protocol.py           # OPP/1.0 framing and canonical JSON
│   ├── crypto.py             # Ed25519 key generation/signature checks
│   ├── store.py              # atomic local wallet persistence
│   └── service.py            # receiver-side verification and replay checks
├── docs/
│   ├── PROTOCOL.md           # full protocol specification
│   ├── ARCHITECTURE.md       # layers, components and flow
│   └── TESTING.md            # test cases and demo/troubleshooting
└── tests/
    ├── test_protocol.py      # message framing tests
    └── test_service.py       # payment, signature, replay and idempotency tests
```

## Packet flow at a glance

```text
Alice wallet                         Bob wallet / receiver
    |                                        |
    |---- TCP connection on local network -->|
    |                                        |
    | PAYMENT_REQUEST + Alice signature      |
    |--------------------------------------->|
    |                      validate version, fields, expiry,
    |                      signature, amount, sequence and ID
    |                                        |
    |                      atomically credit Bob and save receipt
    |                                        |
    | PAYMENT_ACK + Bob signature            |
    |<---------------------------------------|
    | verify Bob's signature; mark pending   |
    | transaction accepted                  |
```

The detailed packet format, error codes, assumptions and future reconciliation design are in [`docs/PROTOCOL.md`](docs/PROTOCOL.md).

## Run tests

```bash
python -m unittest discover -s tests -v
```

## GitHub publishing

Create an empty repository on GitHub (for example, `offline-payment-protocol-cn`), then upload these project files. Do **not** upload `data/`, private keys, wallet JSON files, or screenshots containing private information. A research example for further reading is [DOLE, an offline peer-to-peer payment proof of concept](https://github.com/dominikkipfer/DOLE); it is a separate research project, not a dependency of this implementation.

## Possible extensions for a final-year version

- A reconciliation API and conflict report for duplicate offline spends.
- A QR-code transport for exchanging signed payment requests when TCP is unavailable.
- Bluetooth/NFC transport adapter while keeping the same application-layer message schema.
- A sequence diagram, packet capture, and latency/packet-size measurements for the CN report.
- A certificate-based public-key trust model instead of manually copying demo public keys.
