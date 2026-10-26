"""Small, atomic JSON store for the classroom prototype."""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from .crypto import create_keypair

_USER_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def data_root() -> Path:
    return Path(os.environ.get("OPP_DATA_DIR", "data")).expanduser().resolve()


def user_path(user_id: str) -> Path:
    validate_user_id(user_id)
    return data_root() / "wallets" / f"{user_id}.json"


def private_key_path(user_id: str) -> Path:
    validate_user_id(user_id)
    return data_root() / "keys" / f"{user_id}.private.pem"


def public_key_path(user_id: str) -> Path:
    validate_user_id(user_id)
    return data_root() / "keys" / f"{user_id}.public.pem"


def validate_user_id(user_id: str) -> None:
    if not _USER_RE.fullmatch(user_id):
        raise ValueError("User ID must be 1–32 characters: letters, digits, underscore or hyphen")


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Invalid JSON object in {path}")
    return value


def initialize_user(user_id: str, balance_paise: int) -> None:
    validate_user_id(user_id)
    if balance_paise < 0:
        raise ValueError("Starting balance cannot be negative")
    wallet_file = user_path(user_id)
    private_file = private_key_path(user_id)
    public_file = public_key_path(user_id)
    if wallet_file.exists() or private_file.exists() or public_file.exists():
        raise FileExistsError(f"User '{user_id}' already exists in this data directory")
    create_keypair(private_file, public_file)
    atomic_write_json(wallet_file, {
        "user_id": user_id,
        "balance_paise": balance_paise,
        "next_sequence": 1,
        "pending": {},
        "received_transactions": {},
        "seen_sequences": [],
    })


def load_wallet(user_id: str) -> dict[str, Any]:
    path = user_path(user_id)
    if not path.exists():
        raise FileNotFoundError(f"Wallet '{user_id}' does not exist; run the init command first")
    wallet = read_json(path)
    if wallet.get("user_id") != user_id:
        raise ValueError("Wallet user ID does not match its filename")
    return wallet


def save_wallet(wallet: dict[str, Any]) -> None:
    atomic_write_json(user_path(str(wallet["user_id"])), wallet)
