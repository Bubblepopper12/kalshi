"""Read-only Kalshi Trade API client for public market data.

Series, events, markets and order books. The client sends no credentials and
refuses any method other than GET, so the research jobs can never place, change
or cancel orders. Trading lives separately in trading/, behind approval.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import httpx

from ..config import Settings

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}


class KalshiReadOnlyClient:
    def __init__(
        self,
        base_url: str | None = None,
        requests_per_second: float = 8.0,
        transport: httpx.BaseTransport | None = None,
        max_retries: int = 4,
    ) -> None:
        settings = Settings.from_env()
        self.base_url = (base_url or settings.kalshi_api_base).rstrip("/")
        self._min_interval = 1.0 / requests_per_second if requests_per_second > 0 else 0.0
        self._last_request = 0.0
        self._max_retries = max_retries
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(20.0),
            headers={"Accept": "application/json", "User-Agent": "picks-engine/0.1 (read-only)"},
            transport=transport,
            event_hooks={"request": [self._guard]},
        )

    @staticmethod
    def _guard(request: httpx.Request) -> None:
        if request.method != "GET":
            raise PermissionError("picks-engine is read-only: only GET requests to Kalshi are allowed")
        if "authorization" in request.headers or any(
            h.lower().startswith("kalshi-access") for h in request.headers
        ):
            raise PermissionError("picks-engine never sends Kalshi credentials")

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "KalshiReadOnlyClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------ transport

    def _throttle(self) -> None:
        wait = self._min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        for attempt in range(self._max_retries + 1):
            self._throttle()
            try:
                resp = self._http.get(path, params=params)
            except httpx.TransportError as exc:
                if attempt == self._max_retries:
                    raise
                log.warning("Kalshi %s failed (%s); retrying", path, exc)
            else:
                if resp.status_code not in RETRY_STATUS:
                    resp.raise_for_status()
                    return resp.json()
                if attempt == self._max_retries:
                    resp.raise_for_status()
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    time.sleep(min(int(retry_after), 30))
                    continue
            time.sleep(min(2 ** (attempt + 1), 16))
        raise RuntimeError("unreachable")

    def paginate(self, path: str, key: str, params: dict[str, Any] | None = None) -> Iterator[dict]:
        params = dict(params or {})
        while True:
            data = self.get(path, params)
            yield from data.get(key) or []
            cursor = data.get("cursor")
            if not cursor:
                return
            params["cursor"] = cursor

    # ------------------------------------------------------------ endpoints

    def series(self, category: str | None = None) -> list[dict]:
        return self.get("/series", {"category": category}).get("series") or []

    def events(
        self, series_ticker: str, status: str | None = "open", with_nested_markets: bool = True
    ) -> Iterator[dict]:
        return self.paginate(
            "/events",
            "events",
            {
                "series_ticker": series_ticker,
                "status": status,
                "with_nested_markets": "true" if with_nested_markets else None,
                "limit": 200,
            },
        )

    def markets(
        self, series_ticker: str | None = None, event_ticker: str | None = None, status: str | None = "open",
        min_close_ts: int | None = None,
    ) -> Iterator[dict]:
        return self.paginate(
            "/markets",
            "markets",
            {"series_ticker": series_ticker, "event_ticker": event_ticker, "status": status, "limit": 1000,
             "min_close_ts": min_close_ts},
        )

    def market(self, ticker: str) -> dict:
        return self.get(f"/markets/{ticker}").get("market") or {}

    def candlesticks(self, series_ticker: str, ticker: str, start_ts: int, end_ts: int,
                     period_minutes: int = 60) -> list[dict]:
        """Price history for one market: one candle per period (1, 60 or 1440 minutes)."""
        data = self.get(f"/series/{series_ticker}/markets/{ticker}/candlesticks",
                        {"start_ts": int(start_ts), "end_ts": int(end_ts), "period_interval": period_minutes})
        return data.get("candlesticks") or []

    def orderbook(self, ticker: str, depth: int | None = None) -> "OrderBook":
        data = self.get(f"/markets/{ticker}/orderbook", {"depth": depth})
        return OrderBook.from_api(data)


# ---------------------------------------------------------------- payload helpers


def price_field(obj: dict, name: str) -> Decimal | None:
    """Read a price as dollars (0-1).

    Kalshi returns legacy integer cents (`yes_bid: 54`) and, on newer payloads,
    fixed-point dollar strings (`yes_bid_dollars: "0.5400"`). Prefer the dollar field.
    """
    dollars = obj.get(f"{name}_dollars")
    if dollars not in (None, ""):
        return Decimal(str(dollars))
    cents = obj.get(name)
    if cents is None or cents == "":
        return None
    return Decimal(str(cents)) / 100


def count_field(obj: dict, name: str) -> int | None:
    for key in (name, f"{name}_fp"):
        val = obj.get(key)
        if val not in (None, ""):
            return int(Decimal(str(val)))
    return None


class OrderBook:
    """Kalshi books list resting bids on each side. A YES ask at price p is a NO bid at 1 - p."""

    def __init__(self, yes_bids: list[tuple[Decimal, int]], no_bids: list[tuple[Decimal, int]]):
        self.yes_bids = sorted(yes_bids, key=lambda lvl: lvl[0], reverse=True)
        self.no_bids = sorted(no_bids, key=lambda lvl: lvl[0], reverse=True)

    @classmethod
    def from_api(cls, data: dict) -> "OrderBook":
        book = data.get("orderbook") or data.get("orderbook_fp") or {}

        def levels(side: str) -> list[tuple[Decimal, int]]:
            dollars = book.get(f"{side}_dollars")
            if dollars:
                return [(Decimal(str(p)), int(Decimal(str(q)))) for p, q in dollars]
            return [(Decimal(str(p)) / 100, int(Decimal(str(q)))) for p, q in (book.get(side) or [])]

        return cls(levels("yes"), levels("no"))

    def best_ask(self, side: str) -> Decimal | None:
        opposite = self.no_bids if side == "yes" else self.yes_bids
        return (Decimal(1) - opposite[0][0]) if opposite else None

    def best_bid(self, side: str) -> Decimal | None:
        own = self.yes_bids if side == "yes" else self.no_bids
        return own[0][0] if own else None

    def depth_at_or_below(self, side: str, max_price: Decimal) -> int:
        """Contracts you could buy on `side` paying at most max_price each."""
        opposite = self.no_bids if side == "yes" else self.yes_bids
        return sum(q for p, q in opposite if Decimal(1) - p <= max_price)

    def to_json(self) -> dict:
        return {
            "yes_bids": [[str(p), q] for p, q in self.yes_bids],
            "no_bids": [[str(p), q] for p, q in self.no_bids],
        }
