"""Today's picks: where Kalshi sells an outcome for less than the sportsbooks think it's worth.

For each Kalshi full-game winner market:
  1. find the same game in the sportsbook feed (date + both team names),
  2. remove each book's margin (de-vig) and take the median fair chance,
  3. compare with the Kalshi YES ask plus Kalshi's fee,
  4. edge = fair chance - cost. A pick needs edge >= min_edge, at least two
     books, and a game that hasn't started.
Sizing is quarter-Kelly on the cash balance, capped by the per-bet limit.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal

from ..kalshi.classify import parse_event_ticker
from ..kalshi.client import price_field
from ..pricing.devig import devig
from ..pricing.fees import fee_per_contract
from ..pricing.kelly import stake_fraction
from .teams import assign, is_draw

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    _ET = timezone.utc


@dataclass
class BookView:
    fair: float  # median de-vigged chance across books
    books: list[str]  # bookmaker names used
    low: float
    high: float
    updated: datetime | None


@dataclass
class Pick:
    ticker: str
    event_ticker: str
    game: str
    day: date | None
    starts: datetime | None
    outcome: str  # "Philadelphia wins" / "It ends in a draw"
    ask: Decimal
    fee: Decimal
    fair: float
    edge: float
    books: list[str]
    book_low: float
    book_high: float
    odds_updated: datetime | None
    contracts: int = 0
    stake: Decimal = Decimal(0)
    notes: list[str] = field(default_factory=list)

    @property
    def cost(self) -> Decimal:
        return self.ask + self.fee


@dataclass
class PicksResult:
    picks: list[Pick]  # edge >= min_edge, best first
    near: list[Pick]  # 0 < edge < min_edge
    games_checked: int
    games_matched: int
    unmatched: list[str]


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def book_views(odds_event: dict, three_way: bool) -> dict[str, BookView]:
    """Outcome name ('home'/'away'/'draw') -> consensus across bookmakers."""
    home, away = odds_event.get("home_team", ""), odds_event.get("away_team", "")
    per: dict[str, list[float]] = {"home": [], "away": [], "draw": []}
    names: list[str] = []
    latest: datetime | None = None
    for bk in odds_event.get("bookmakers") or []:
        market = next((m for m in bk.get("markets") or [] if m.get("key") == "h2h"), None)
        if not market:
            continue
        prices = {}
        for o in market.get("outcomes") or []:
            nm = o.get("name", "")
            key = "home" if nm == home else "away" if nm == away else "draw" if is_draw(nm) else None
            if key and o.get("price") is not None:
                prices[key] = float(o["price"])
        wanted = ["home", "away", "draw"] if three_way else ["home", "away"]
        if any(k not in prices for k in wanted):
            continue
        try:
            fair = devig([prices[k] for k in wanted])
        except ValueError:
            continue
        for k, p in zip(wanted, fair):
            per[k].append(p)
        names.append(bk.get("title") or bk.get("key") or "?")
        upd = _parse(market.get("last_update") or bk.get("last_update"))
        if upd and (latest is None or upd > latest):
            latest = upd
    return {k: BookView(statistics.median(v), names, min(v), max(v), latest) for k, v in per.items() if v}


def _same_day(kalshi_day: date | None, commence: datetime | None) -> bool:
    if kalshi_day is None or commence is None:
        return True
    local = commence.astimezone(_ET).date()
    return abs((local - kalshi_day).days) <= 1


def find_game(kalshi_event: dict, odds_events: list[dict]) -> tuple[dict, dict[str, str]] | None:
    names = [m.get("yes_sub_title") or "" for m in kalshi_event.get("markets") or []]
    day, _ = parse_event_ticker(kalshi_event.get("event_ticker") or "")
    found = []
    for oe in odds_events:
        if not _same_day(day, _parse(oe.get("commence_time"))):
            continue
        mapping = assign(names, oe.get("home_team", ""), oe.get("away_team", ""))
        if mapping:
            found.append((oe, mapping))
    return found[0] if len(found) == 1 else None


def size(pick: Pick, cash: Decimal | None, max_order: float, kelly_fraction: float = 0.25) -> None:
    """Fill in suggested contracts and stake (quarter-Kelly of cash, capped at the per-bet limit)."""
    cost = float(pick.cost)
    frac = stake_fraction(pick.fair, cost, kelly_fraction=kelly_fraction, cap=1.0)
    budget = Decimal(str(max_order))
    if cash is not None:
        budget = min(budget, (cash * Decimal(str(frac))), cash)
    n = int((budget / pick.cost).to_integral_value(rounding=ROUND_DOWN)) if pick.cost > 0 else 0
    pick.contracts = max(n, 0)
    pick.stake = (pick.cost * pick.contracts).quantize(Decimal("0.01"))


def build_picks(kalshi_events: list[dict], odds_events: list[dict], *, three_way: bool,
                min_edge: float = 0.03, fee_rate: float = 0.07, fee_contracts: int = 10,
                now: datetime | None = None) -> PicksResult:
    now = now or datetime.now(timezone.utc)
    picks, near, unmatched = [], [], []
    checked = matched = 0
    for ev in kalshi_events:
        markets = [m for m in ev.get("markets") or [] if (m.get("status") or "active") in ("active", "open")]
        if not markets:
            continue
        checked += 1
        game = find_game(ev, odds_events)
        if game is None:
            unmatched.append(ev.get("title") or ev.get("event_ticker") or "?")
            continue
        oe, mapping = game
        starts = _parse(oe.get("commence_time"))
        if starts and starts <= now:
            continue  # already started: in-game prices are a different thing
        matched += 1
        views = book_views(oe, three_way)
        day, _ = parse_event_ticker(ev.get("event_ticker") or "")
        for m in markets:
            name = m.get("yes_sub_title") or ""
            side = "draw" if is_draw(name) else mapping.get(name)
            view = views.get(side or "")
            ask = price_field(m, "yes_ask")
            if view is None or ask is None or not (0 < ask < 1) or len(view.books) < 2:
                continue
            fee = Decimal(str(fee_per_contract(float(ask), fee_contracts, fee_rate))).quantize(Decimal("0.0001"))
            edge = view.fair - float(ask + fee)
            outcome = ("It ends in a draw" if name.lower() == "draw" else "It ends in a tie") if side == "draw" \
                else f"{name} wins"
            p = Pick(ticker=m["ticker"], event_ticker=ev.get("event_ticker") or "", game=ev.get("title") or "",
                     day=day, starts=starts, outcome=outcome, ask=ask, fee=fee, fair=view.fair, edge=edge,
                     books=view.books, book_low=view.low, book_high=view.high, odds_updated=view.updated)
            if view.updated and now - view.updated > timedelta(minutes=60):
                p.notes.append("Sportsbook prices are over an hour old.")
            if edge >= min_edge:
                picks.append(p)
            elif edge > 0:
                near.append(p)
    picks.sort(key=lambda p: p.edge, reverse=True)
    near.sort(key=lambda p: p.edge, reverse=True)
    return PicksResult(picks, near, checked, matched, unmatched)
