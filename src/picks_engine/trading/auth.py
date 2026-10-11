"""Kalshi API-key request signing.

Kalshi authenticates each request with three headers:
  KALSHI-ACCESS-KEY        the API key ID
  KALSHI-ACCESS-TIMESTAMP  milliseconds since the epoch
  KALSHI-ACCESS-SIGNATURE  base64 signature of timestamp + METHOD + path

Kalshi issues two key types: RSA (signed with RSA-PSS, SHA-256, digest-length
salt) and, since September 2026, Ed25519 (plain Ed25519 over the same text).
Both can arrive as "-----BEGIN PRIVATE KEY-----", so the type is read from the
key itself, not the header.

The path is the full URL path (e.g. /trade-api/v2/portfolio/orders) without the
query string. The private key stays in a file on the machine running the bot;
it is never stored in the database or printed.
"""

from __future__ import annotations

import base64
import os
import stat
import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa

SigningKey = rsa.RSAPrivateKey | ed25519.Ed25519PrivateKey


class KalshiSigner:
    def __init__(self, key_id: str, private_key: SigningKey):
        if not key_id:
            raise ValueError("Kalshi API key ID is empty")
        if not isinstance(private_key, (rsa.RSAPrivateKey, ed25519.Ed25519PrivateKey)):
            raise ValueError(
                f"Kalshi keys are RSA or Ed25519; this file holds a {type(private_key).__name__}. "
                "Check that KALSHI_PRIVATE_KEY_PATH points at the key Kalshi gave you."
            )
        self.key_id = key_id
        self._key = private_key

    @classmethod
    def from_file(cls, key_id: str, path: str | os.PathLike) -> "KalshiSigner":
        p = Path(path).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"Kalshi private key file not found: {p}")
        if os.name == "posix" and p.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise PermissionError(
                f"{p} can be read by other users on this machine. Run: chmod 600 {p}"
            )
        return cls.from_pem(key_id, p.read_bytes(), source=str(p))

    @classmethod
    def from_pem(cls, key_id: str, pem: bytes | str, source: str = "The private key") -> "KalshiSigner":
        if isinstance(pem, str):
            # Settings UIs sometimes store newlines as a literal "\n".
            pem = pem.strip().replace("\\n", "\n").encode()
        try:
            key = serialization.load_pem_private_key(pem, password=None)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{source} isn't a readable private key ({exc}). "
                             "It should start with -----BEGIN and end with -----END lines.") from None
        return cls(key_id, key)

    @property
    def key_type(self) -> str:
        return "ed25519" if isinstance(self._key, ed25519.Ed25519PrivateKey) else "rsa"

    def headers(self, method: str, path: str, timestamp_ms: int | None = None) -> dict[str, str]:
        ts = str(timestamp_ms if timestamp_ms is not None else int(time.time() * 1000))
        message = (ts + method.upper() + path.split("?")[0]).encode()
        if isinstance(self._key, ed25519.Ed25519PrivateKey):
            signature = self._key.sign(message)
        else:
            signature = self._key.sign(
                message,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                hashes.SHA256(),
            )
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
        }
