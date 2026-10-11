"""Kalshi API-key request signing.

Kalshi authenticates each request with three headers:
  KALSHI-ACCESS-KEY        the API key ID
  KALSHI-ACCESS-TIMESTAMP  milliseconds since the epoch
  KALSHI-ACCESS-SIGNATURE  base64 RSA-PSS (SHA-256) signature of timestamp + METHOD + path

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
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class KalshiSigner:
    def __init__(self, key_id: str, private_key: rsa.RSAPrivateKey):
        if not key_id:
            raise ValueError("Kalshi API key ID is empty")
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
        key = serialization.load_pem_private_key(p.read_bytes(), password=None)
        if not isinstance(key, rsa.RSAPrivateKey):
            raise ValueError("Kalshi private key must be an RSA key")
        return cls(key_id, key)

    def headers(self, method: str, path: str, timestamp_ms: int | None = None) -> dict[str, str]:
        ts = str(timestamp_ms if timestamp_ms is not None else int(time.time() * 1000))
        message = (ts + method.upper() + path.split("?")[0]).encode()
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
