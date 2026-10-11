"""Who may use the web app: password + authenticator code, signed sessions and tickets.

Nothing here talks to Kalshi. Tokens are HMAC-signed with a key derived from the
password, the two-step secret and the Kalshi key, so changing any of those logs
everyone out and voids every unsent ticket.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time

from ..config import Settings

MIN_PASSWORD_LENGTH = 16
SESSION_HOURS = 12
COOKIE = "picks_session"


def _password() -> str:
    return os.environ.get("APP_PASSWORD", "")


def _totp_secret() -> str:
    return os.environ.get("APP_TOTP_SECRET", "").replace(" ", "").upper()


def totp_code(secret_b32: str, at: float | None = None, step: int = 30) -> str:
    """RFC 6238 six-digit code (what authenticator apps show)."""
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    counter = int((time.time() if at is None else at) // step)
    mac = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    return f"{(int.from_bytes(mac[offset:offset + 4], 'big') & 0x7FFFFFFF) % 1_000_000:06d}"


def totp_ok(secret_b32: str, code: str, at: float | None = None) -> bool:
    code = re.sub(r"\s", "", code or "")
    if not re.fullmatch(r"\d{6}", code):
        return False
    now = time.time() if at is None else at
    return any(hmac.compare_digest(code, totp_code(secret_b32, now + drift)) for drift in (-30, 0, 30))


def _secret(settings: Settings) -> bytes:
    material = "\0".join([_password(), _totp_secret(), settings.kalshi_private_key or "",
                          settings.kalshi_api_key_id or ""])
    return hashlib.sha256(b"picks-web-v1\0" + material.encode()).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(settings: Settings, payload: dict) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    mac = _b64(hmac.new(_secret(settings), body.encode(), hashlib.sha256).digest())
    return f"{body}.{mac}"


def verify(settings: Settings, token: str | None, kind: str) -> dict | None:
    if not token or token.count(".") != 1:
        return None
    body, mac = token.split(".")
    good = _b64(hmac.new(_secret(settings), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(mac, good):
        return None
    try:
        payload = json.loads(_unb64(body))
    except ValueError:
        return None
    if payload.get("k") != kind or payload.get("exp", 0) < time.time():
        return None
    return payload
