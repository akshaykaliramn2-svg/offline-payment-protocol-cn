# Testing and Troubleshooting

## Unit tests

Run from the repository root:

```bash
python -m unittest discover -s tests -v
```

The tests cover the TCP-frame encoding/decoding path, Ed25519 signature verification, normal payment acceptance, duplicate-transaction idempotency, and replay rejection.

## Manual scenarios

| Scenario | How to test | Expected result |
|---|---|---|
| Valid payment | Alice pays Bob ₹12.50 | Alice balance drops, Bob balance rises, signed receipt is stored |
| Insufficient balance | Pay more than Alice's current balance | Client refuses before reserving funds |
| Invalid signature | Alter a payload after signing in a test | Receiver rejects it |
| Duplicate request | Send the exact same signed request again to the same receiver | Same saved receipt; balance is not credited twice |
| Sequence replay | Send a different transaction using an already accepted payer sequence | Receiver returns a signed `REPLAY` error |
| Wrong receiver | Request has a different `payee` than the receiver | Signed `WRONG_RECIPIENT` error |
| Network unavailable | Stop the receiver and attempt payment | TCP connect failure happens before funds are reserved |
| Response lost/timeout | Simulate a timeout after the request may have been delivered | Sender leaves the transaction pending; do not blindly create another payment |

## Using separate data directories

`OPP_DATA_DIR` selects the local storage root. Each device should have a separate directory and separate private key. Example on macOS/Linux:

```bash
export OPP_DATA_DIR="$HOME/opp-alice-data"
python -m opp init alice --balance 100.00
```

PowerShell example:

```powershell
$env:OPP_DATA_DIR = "$HOME\opp-alice-data"
python -m opp init alice --balance 100.00
```

On Bob's machine, use a different directory and run `python -m opp init bob --balance 0.00`. Copy public keys only, never the private key. Because this is a demo, public-key identity is trusted through manual exchange rather than a certificate authority.

## Common errors

- **`User already exists`:** choose a new user ID or use a fresh `OPP_DATA_DIR` for a clean test.
- **`Connection refused` / timeout:** confirm Bob's receiver is running, the host/port are correct, both machines share a local network, and the private-network firewall permits the port.
- **Missing public key:** copy the intended peer's `.public.pem` file into the local `data/keys/` folder (or the `keys/` folder in the selected data directory).
- **Invalid signature:** check that the public key belongs to the same account and that message fields were not changed after signing.
- **Payment remains pending:** this represents an uncertain network outcome; do not assume the receiver rejected it. This classroom version does not include a full status-query/reconciliation command.

## Suggested screenshots for the CN report

1. Repository tree in GitHub.
2. Bob receiver listening on local TCP port.
3. Alice sending a payment and receiving a signed acknowledgment.
4. Balance before and after payment for both demo users.
5. Unit test output.
6. Optional Wireshark capture showing TCP handshake and application bytes; redact local personal IP details if sharing publicly.
