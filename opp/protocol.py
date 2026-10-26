"""OPP/1.0 wire framing and canonical JSON helpers."""
from __future__ import annotations

import json
import socket
import struct
from typing import Any

MAGIC = "OPP"
VERSION = "1.0"
MAX_FRAME_BYTES = 64 * 1024
_HEADER = struct.Struct("!I")  # 4-byte unsigned length, network byte order


class ProtocolError(ValueError):
    """Raised when a wire message is malformed or out of bounds."""


def canonical_json_bytes(value: Any) -> bytes:
    """Return stable JSON bytes for signing and hashing."""
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"Message is not JSON serializable: {exc}") from exc


def make_message(message_type: str, payload: dict[str, Any], message_id: str) -> dict[str, Any]:
    return {
        "protocol": MAGIC,
        "version": VERSION,
        "type": message_type,
        "message_id": message_id,
        "payload": payload,
    }


def _recv_exact(sock: socket.socket, count: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < count:
        part = sock.recv(count - len(chunks))
        if not part:
            raise ConnectionError("Peer closed the connection before a full frame arrived")
        chunks.extend(part)
    return bytes(chunks)


def send_frame(sock: socket.socket, message: dict[str, Any]) -> None:
    body = canonical_json_bytes(message)
    if not body or len(body) > MAX_FRAME_BYTES:
        raise ProtocolError(f"Frame size must be between 1 and {MAX_FRAME_BYTES} bytes")
    sock.sendall(_HEADER.pack(len(body)) + body)


def recv_frame(sock: socket.socket) -> dict[str, Any]:
    header = _recv_exact(sock, _HEADER.size)
    (length,) = _HEADER.unpack(header)
    if length < 1 or length > MAX_FRAME_BYTES:
        raise ProtocolError(f"Invalid frame length: {length}")
    body = _recv_exact(sock, length)
    try:
        obj = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("Frame does not contain valid UTF-8 JSON") from exc
    if not isinstance(obj, dict):
        raise ProtocolError("Top-level message must be a JSON object")
    if obj.get("protocol") != MAGIC or obj.get("version") != VERSION:
        raise ProtocolError("Unsupported protocol name or version")
    if not isinstance(obj.get("type"), str) or not isinstance(obj.get("payload"), dict):
        raise ProtocolError("Missing or invalid type/payload field")
    return obj
