"""Ed25519 key handling and message signatures."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .protocol import canonical_json_bytes


class SignatureError(ValueError):
    """Raised when a signed message cannot be authenticated."""


def create_keypair(private_path: Path, public_path: Path) -> None:
    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    if private_path.exists() or public_path.exists():
        raise FileExistsError("Key files already exist; refusing to overwrite them")
    private_key = Ed25519PrivateKey.generate()
    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    try:
        private_path.chmod(0o600)
    except OSError:
        pass  # Windows does not support POSIX permission bits in the same way.
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )


def load_private_key(path: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise SignatureError("Expected an Ed25519 private key")
    return key


def load_public_key(path: Path) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise SignatureError("Expected an Ed25519 public key")
    return key


def sign_dict(private_key: Ed25519PrivateKey, value: dict[str, Any]) -> str:
    signature = private_key.sign(canonical_json_bytes(value))
    return base64.b64encode(signature).decode("ascii")


def verify_dict(public_key: Ed25519PublicKey, value: dict[str, Any], signature_b64: str) -> None:
    try:
        signature = base64.b64decode(signature_b64, validate=True)
        public_key.verify(signature, canonical_json_bytes(value))
    except (ValueError, InvalidSignature) as exc:
        raise SignatureError("Signature verification failed") from exc
