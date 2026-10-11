"""Authenticated Kalshi client, limited to the few calls the bot needs.

Allowed: read the portfolio (balance, positions, orders, fills), create an
order, cancel an order. Every other authenticated call is refused before it is
sent. This client is only ever called from trading/orders.py, after a ticket
has been approved and has passed every limit check.
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import Any

import httpx

from ..config import KALSHI_TRADING_HOSTS, Settings
from .auth import KalshiSigner

log = logging.getLogger(__name__)

_ALLOWED = [
    ("GET", re.compile(r"/portfolio/(balance|positions|orders|fills)")),
    ("GET", re.compile(r"/portfolio/orders/[A-Za-z0-9-]+")),
    ("POST", re.compile(r"/portfolio/orders")),
    ("DELETE", re.compile(r"/portfolio/orders/[A-Za-z0-9-]+")),
]


class TradingNotConfigured(RuntimeError):
    pass


def trading_base_url(settings: Settings) -> str:
    if settings.kalshi_env not in KALSHI_TRADING_HOSTS:
        raise TradingNotConfigured(f"KALSHI_ENV must be 'demo' or 'live', not {settings.kalshi_env!r}")
    return (settings.kalshi_trading_base or KALSHI_TRADING_HOSTS[settings.kalshi_env]).rstrip("/")


class KalshiTradingClient:
    def __init__(self, base_url: str, signer: KalshiSigner, env: str,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.env = env
        self.base_url = base_url.rstrip("/")
        self._prefix = httpx.URL(self.base_url).path.rstrip("/")
        self._signer = signer
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(20.0),
            headers={"Accept": "application/json", "User-Agent": "picks-engine/0.2"},
            transport=transport,
        )

    @classmethod
    def from_settings(cls, settings: Settings, transport: httpx.BaseTransport | None = None) -> "KalshiTradingClient":
        if not settings.trading_keys_set:
            raise TradingNotConfigured(
                "Set KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PATH (or KALSHI_PRIVATE_KEY) for a key made on "
                + ("demo.kalshi.co" if settings.kalshi_env == "demo" else "kalshi.com") + "."
            )
        if settings.kalshi_private_key:
            signer = KalshiSigner.from_pem(settings.kalshi_api_key_id, settings.kalshi_private_key,
                                           source="KALSHI_PRIVATE_KEY")
        else:
            signer = KalshiSigner.from_file(settings.kalshi_api_key_id, settings.kalshi_private_key_path)
        return cls(trading_base_url(settings), signer, settings.kalshi_env, transport)

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _request(self, method: str, path: str, *, params: dict | None = None,
                 json: dict | None = None) -> dict[str, Any]:
        if not any(m == method and rx.fullmatch(path) for m, rx in _ALLOWED):
            raise PermissionError(f"{method} {path} is not something this bot is allowed to do")
        headers = self._signer.headers(method, self._prefix + path)
        resp = self._http.request(method, path, params=params, json=json, headers=headers)
        if resp.status_code >= 400:
            raise KalshiAPIError(resp.status_code, resp.text[:500])
        return resp.json() if resp.content else {}

    # ------------------------------------------------------------ reads

    def balance_dollars(self) -> Decimal:
        data = self._request("GET", "/portfolio/balance")
        if data.get("balance_dollars") not in (None, ""):
            return Decimal(str(data["balance_dollars"]))
        return Decimal(str(data.get("balance", 0))) / 100

    def positions(self) -> list[dict]:
        data = self._request("GET", "/portfolio/positions", params={"limit": 200})
        return data.get("market_positions") or []

    def orders(self, status: str | None = "resting") -> list[dict]:
        params = {"limit": 200, **({"status": status} if status else {})}
        return self._request("GET", "/portfolio/orders", params=params).get("orders") or []

    def order(self, order_id: str) -> dict:
        return self._request("GET", f"/portfolio/orders/{order_id}").get("order") or {}

    def fills(self, min_ts: int | None = None) -> list[dict]:
        params = {"limit": 200, **({"min_ts": min_ts} if min_ts else {})}
        return self._request("GET", "/portfolio/fills", params=params).get("fills") or []

    # ------------------------------------------------------------ writes (only via trading/orders.py)

    def create_limit_buy(self, *, ticker: str, side: str, count: int, price: Decimal,
                         client_order_id: str, expiration_ts: int | None) -> dict:
        if side not in ("yes", "no"):
            raise ValueError("side must be yes or no")
        cents = int((price * 100).to_integral_value())
        body: dict[str, Any] = {
            "ticker": ticker,
            "client_order_id": client_order_id,
            "action": "buy",
            "side": side,
            "type": "limit",
            "count": int(count),
            f"{side}_price": cents,
        }
        if expiration_ts:
            body["expiration_ts"] = int(expiration_ts)
        return self._request("POST", "/portfolio/orders", json=body)

    def cancel(self, order_id: str) -> dict:
        return self._request("DELETE", f"/portfolio/orders/{order_id}")


class KalshiAPIError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"Kalshi returned HTTP {status}: {body}")
        self.status = status
        self.body = body
