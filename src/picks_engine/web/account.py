"""Read the account from Kalshi and put names on everything (no database)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from ..config import Settings
from ..kalshi.classify import classify
from ..kalshi.client import KalshiReadOnlyClient, count_field, price_field
from ..trading.client import KalshiTradingClient
from ..trading.limits import max_cost
from .describe import outcome

MAX_NAME_LOOKUPS = 25


def committed_today(client: KalshiTradingClient, settings: Settings) -> tuple[Decimal, int]:
    """Money today's buys could use (fills since UTC midnight + resting buy orders), and the open-order count."""
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    total = Decimal(0)
    for f in client.fills(min_ts=int(start.timestamp())):
        if (f.get("action") or "buy") != "buy":
            continue
        created = f.get("created_time")
        if created:
            try:
                if datetime.fromisoformat(created.replace("Z", "+00:00")) < start:
                    continue
            except ValueError:
                pass
        side = f.get("side") or "yes"
        px, n = price_field(f, f"{side}_price"), count_field(f, "count")
        if px is not None and n:
            total += max_cost(n, px, settings.kalshi_fee_rate)
    resting = [o for o in client.orders("resting") if (o.get("action") or "buy") == "buy"]
    for o in resting:
        side = o.get("side") or "yes"
        px = price_field(o, f"{side}_price")
        n = count_field(o, "remaining_count") or count_field(o, "count")
        if px is not None and n:
            total += max_cost(n, px, settings.kalshi_fee_rate)
    return total, len(resting)


@dataclass
class MarketName:
    ticker: str
    statement: str  # what YES means, e.g. "Philadelphia wins"
    question: str  # Kalshi's title, e.g. "Jacksonville at Philadelphia Winner?"
    yes_bid: Decimal | None = None
    no_bid: Decimal | None = None
    yes_ask: Decimal | None = None
    no_ask: Decimal | None = None


def name_market(m: dict) -> MarketName:
    kind = classify(m.get("event_ticker", "").split("-")[0], m.get("title") or "")
    return MarketName(
        ticker=m.get("ticker", ""),
        statement=outcome(m, kind),
        question=(m.get("title") or "").strip(),
        yes_bid=price_field(m, "yes_bid"), no_bid=price_field(m, "no_bid"),
        yes_ask=price_field(m, "yes_ask"), no_ask=price_field(m, "no_ask"),
    )


def lookup_names(rc: KalshiReadOnlyClient, tickers: list[str]) -> dict[str, MarketName]:
    names: dict[str, MarketName] = {}
    for ticker in list(dict.fromkeys(t for t in tickers if t))[:MAX_NAME_LOOKUPS]:
        try:
            m = rc.market(ticker)
        except httpx.HTTPError:
            m = {}
        names[ticker] = name_market(m) if m else MarketName(ticker, ticker, "")
    return names


@dataclass
class Holding:
    name: MarketName
    side: str  # yes | no
    contracts: int

    @property
    def pays_if_right(self) -> Decimal:
        return Decimal(self.contracts)

    @property
    def worth_now(self) -> Decimal | None:
        bid = self.name.yes_bid if self.side == "yes" else self.name.no_bid
        return None if bid is None else (bid * self.contracts).quantize(Decimal("0.01"))


def holdings(positions: list[dict], names: dict[str, MarketName]) -> list[Holding]:
    out = []
    for p in positions:
        n = count_field(p, "position")
        if not n:
            continue
        ticker = p.get("ticker", "")
        out.append(Holding(names.get(ticker) or MarketName(ticker, ticker, ""), "yes" if n > 0 else "no", abs(n)))
    return out
