"""Grade past trades by the math, not by whether they won.

A bet is good when you paid less than it was worth. "Worth" is the fair chance of your side
at the last moment before the game started, the closing line, which pros use to measure skill
because it already contains all the information anyone had. For each fill:

  cost       = price paid + Kalshi's fee per contract (the real fee from the fill when given)
  fair       = Pinnacle's closing no-vig chance (NFL and the soccer leagues, when matched),
               otherwise Kalshi's own mid-price one minute before kickoff
  edge       = fair - cost  (in points: +4 means you paid 4 cents less than it was worth)
  expected   = contracts x edge  (what the bet was worth in dollars when you made it)
  actual     = contracts x (payout - cost) once it settles
  luck       = actual - expected

Kickoff comes from ESPN's scoreboard (or the time in Kalshi's ticker). Bets placed after the
game started have no fair pre-game price and aren't graded. Combos use their earliest leg's
kickoff. Futures (season-long markets) are graded by how far the price has moved since you
bought, and say so.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from .history import _ET, _close
from .kalshi.classify import classify, parse_event_ticker
from .kalshi.client import amount_field, price_field
from .kalshi.leagues import LEAGUES, League
from .live.board import outcome_text
from .live.teams import is_draw
from .pricing.fees import fee_per_contract

LETTERS = ((3.0, "A"), (1.0, "B"), (-1.0, "C"), (-3.0, "D"))  # edge points at or above -> letter; else F
WIDE_SPREAD = Decimal("0.08")


def letter(edge_points: float) -> str:
    return next((g for cut, g in LETTERS if edge_points >= cut), "F")


@dataclass
class Fill:
    ticker: str
    side: str  # yes | no
    action: str  # buy | sell
    contracts: Decimal  # can be fractional
    price: Decimal  # per contract, dollars, for `side`
    fee: Decimal  # per contract, dollars
    at: datetime
    taker: bool

    @property
    def cost(self) -> Decimal:
        """Per contract: what a buy cost, or (for a sell) what you received after the fee, as a negative."""
        return self.price + self.fee if self.action == "buy" else -(self.price - self.fee)


def _when(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_fill(f: dict, taker_rate: float = 0.07, maker_rate: float = 0.0175) -> Fill | None:
    side = f.get("side") or "yes"
    price = price_field(f, f"{side}_price")
    if price is None and f.get(f"{side}_price_fixed") not in (None, ""):
        price = Decimal(str(f[f"{side}_price_fixed"]))
    n = amount_field(f, "count")
    at = _when(f.get("created_time")) or _when(f.get("ts"))
    if price is None or not n or at is None:
        return None
    taker = bool(f.get("is_taker", True))
    fee = None
    raw = f.get("fee_cost")
    if raw not in (None, ""):
        total = Decimal(str(raw))
        if "." not in str(raw):  # whole number: cents
            total /= 100
        fee = total / n
    if fee is None:
        fee = Decimal(str(fee_per_contract(float(price), float(n), taker_rate if taker else maker_rate)))
    return Fill(f.get("ticker", ""), side, f.get("action") or "buy", n, price, fee, at, taker)


def merge_fills(fills: list[tuple[dict, Fill]]) -> list[tuple[dict, Fill]]:
    """One line per order: Kalshi splits an order into several fills (one per seller it matched)."""
    groups: dict[tuple, list[tuple[dict, Fill]]] = {}
    for raw, f in fills:
        key = (raw.get("order_id") or id(raw), f.ticker, f.side, f.action)
        groups.setdefault(key, []).append((raw, f))
    out = []
    for parts in groups.values():
        raw, first = parts[0]
        n = sum((f.contracts for _, f in parts), Decimal(0))
        if n <= 0:
            continue
        price = sum((f.price * f.contracts for _, f in parts), Decimal(0)) / n
        fee = sum((f.fee * f.contracts for _, f in parts), Decimal(0)) / n
        out.append((raw, Fill(first.ticker, first.side, first.action, n, price, fee,
                              min(f.at for _, f in parts), all(f.taker for _, f in parts))))
    return sorted(out, key=lambda x: x[1].at, reverse=True)


def fills_from(raw: list[dict], taker_rate: float = 0.07, maker_rate: float = 0.0175) -> list[Fill]:
    parsed = [(r, f) for r in raw if (f := parse_fill(r, taker_rate, maker_rate)) is not None]
    return [f for _, f in merge_fills(parsed)]


@dataclass
class Grade:
    fill: Fill
    bet: str  # plain words, e.g. "Philadelphia wins"
    question: str
    kind: str  # game | combo | future
    league: str = ""
    start: datetime | None = None
    start_source: str = ""
    kalshi_close: float | None = None  # Kalshi's fair chance of your side before kickoff
    books_close: float | None = None  # Pinnacle's closing no-vig chance of your side
    fair: float | None = None  # the one graded against
    fair_source: str = ""
    result: str = "open"  # won | lost | open
    notes: list[str] = field(default_factory=list)

    @property
    def graded(self) -> bool:
        return self.fair is not None

    @property
    def edge(self) -> float | None:
        """Points per contract: positive = paid less than it was worth (or sold for more)."""
        if self.fair is None:
            return None
        c = float(self.fill.cost)
        return (self.fair - c) * 100 if self.fill.action == "buy" else (-c - self.fair) * 100

    @property
    def letter(self) -> str:
        return letter(self.edge) if self.edge is not None else "–"

    @property
    def expected(self) -> float | None:
        return None if self.edge is None else self.edge / 100 * float(self.fill.contracts)

    @property
    def actual(self) -> float | None:
        if self.result == "open":
            return None
        payout = 1.0 if self.result == "won" else 0.0
        c = float(self.fill.cost)
        per = (payout - c) if self.fill.action == "buy" else (-c - payout)
        return per * float(self.fill.contracts)


@dataclass
class Summary:
    grades: list[Grade]

    @property
    def graded(self) -> list[Grade]:
        return [g for g in self.grades if g.graded]

    @property
    def contracts(self) -> float:
        return sum(float(g.fill.contracts) for g in self.graded)

    @property
    def avg_edge(self) -> float | None:
        n = self.contracts
        return sum(g.edge * float(g.fill.contracts) for g in self.graded) / n if n else None

    @property
    def expected(self) -> float:
        return sum(g.expected for g in self.graded)

    @property
    def beat_close(self) -> int:
        return sum(1 for g in self.graded if g.edge > 0)

    @property
    def settled(self) -> list[Grade]:
        return [g for g in self.graded if g.actual is not None]

    @property
    def actual(self) -> float:
        return sum(g.actual for g in self.settled)

    @property
    def luck(self) -> float:
        return self.actual - sum(g.expected for g in self.settled)

    @property
    def luck_sd(self) -> float:
        """Typical size of luck for these bets (one standard deviation, in dollars)."""
        var = 0.0
        for g in self.settled:
            p = min(max(g.fair, 0.0), 1.0)
            var += (float(g.fill.contracts) ** 2) * p * (1 - p)
        return math.sqrt(var)

    @property
    def letter(self) -> str:
        return letter(self.avg_edge) if self.avg_edge is not None else "–"


# ---------------------------------------------------------------- the lookups grading needs


def league_of(series: str) -> League | None:
    return next((lg for lg in LEAGUES.values() if lg.matches({"ticker": series, "category": "Sports"})), None)


def kind_of(market: dict) -> str:
    event = market.get("event_ticker") or ""
    if market.get("mve_selected_legs") or event.upper().startswith("KXMVE"):
        return "combo"
    k = classify(event.split("-")[0], market.get("title") or "")
    return "game" if k in ("moneyline", "spread", "total", "prop") and parse_event_ticker(event)[0] else "future"


def teams_from(event: dict, markets: list[dict]) -> list[str]:
    """The two teams of a game, from its winner markets ("Philadelphia", "Dallas") or its title."""
    names = [m.get("yes_sub_title") or "" for m in markets]
    names = [n for n in names if n and not is_draw(n) and not re.search(r"\d", n)]
    if len(set(names)) == 2:
        return sorted(set(names))
    title = re.split(r"[:|]| - ", event.get("title") or "")[0]
    parts = re.split(r"\s+(?:at|vs\.?|v\.?|@)\s+", title.strip(), flags=re.I)
    return [p.strip() for p in parts] if len(parts) == 2 else []


def ticker_start(event_ticker: str) -> datetime | None:
    """Some Kalshi tickers carry the kickoff: KXMLBGAME-25JUN041910NYYSEA = Jun 4, 19:10 Eastern."""
    m = re.search(r"-(\d{2})([A-Z]{3})(\d{2})(\d{4})", event_ticker.upper())
    day, _ = parse_event_ticker(event_ticker)
    if not m or day is None:
        return None
    hh, mm = int(m.group(4)[:2]), int(m.group(4)[2:])
    if hh > 23 or mm > 59:
        return None
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=_ET).astimezone(timezone.utc)


def close_mid(candles: list[dict], before: datetime) -> tuple[Decimal | None, Decimal | None]:
    """(yes mid, spread) from the last candle ending at or before `before`."""
    ok = [c for c in candles if c.get("end_period_ts") and int(c["end_period_ts"]) <= before.timestamp()]
    for c in sorted(ok, key=lambda c: int(c["end_period_ts"]), reverse=True):
        bid, ask = _close(c, "yes_bid"), _close(c, "yes_ask")
        if bid is not None and ask is not None and 0 < ask <= 1 and 0 <= bid < 1 and bid <= ask:
            return (bid + ask) / 2, ask - bid
        last = _close(c, "price")
        if last is not None and 0 < last < 1:
            return last, None
    return None, None


@dataclass
class Lookups:
    """Everything grading reads from the outside world, injectable for tests."""

    market: Callable[[str], dict]  # ticker -> Kalshi market
    event: Callable[[str], dict]  # event ticker -> {"event": {...}, "markets": [...]}
    candles: Callable[[str, str, int, int, int], list[dict]]  # series, ticker, start, end, minutes
    start_time: Callable[[str, object, list[str]], datetime | None]  # league, day, teams -> kickoff
    books_close: Callable[[str, dict, list[dict]], float | None] = lambda league, market, siblings: None


def _event_start(lk: Lookups, event_ticker: str, cache: dict) -> tuple[datetime | None, str, str, list[dict]]:
    """(kickoff, how we know, league code, the event's markets)."""
    if event_ticker in cache:
        return cache[event_ticker]
    series = event_ticker.split("-")[0]
    lg = league_of(series)
    try:
        data = lk.event(event_ticker)
    except Exception:
        data = {}
    markets = data.get("markets") or (data.get("event") or {}).get("markets") or []
    out: tuple = (None, "", lg.code if lg else "", markets)
    if (t := ticker_start(event_ticker)) is not None:
        out = (t, "Kalshi's ticker", out[2], markets)
    elif lg is not None:
        day, _ = parse_event_ticker(event_ticker)
        teams = teams_from(data.get("event") or {}, markets)
        start = lk.start_time(lg.code, day, teams)
        if start is not None:
            out = (start, "ESPN", lg.code, markets)
    cache[event_ticker] = out
    return out


def grade(fills: list[Fill], lk: Lookups, now: datetime | None = None) -> Summary:
    now = now or datetime.now(timezone.utc)
    markets: dict[str, dict] = {}
    events: dict = {}
    closes: dict[tuple[str, int], tuple[Decimal | None, Decimal | None]] = {}
    grades = []
    for f in sorted(fills, key=lambda f: f.at, reverse=True):
        if f.ticker not in markets:
            try:
                markets[f.ticker] = lk.market(f.ticker) or {}
            except Exception:
                markets[f.ticker] = {}
        m = markets[f.ticker]
        kind = kind_of(m) if m else "game"
        bet = outcome_text(m, classify(f.ticker.split("-")[0], m.get("title") or "")) if m else f.ticker
        g = Grade(f, bet, (m.get("title") or "").strip(), kind)
        result = (m.get("result") or "").lower()
        if result in ("yes", "no"):
            g.result = "won" if result == f.side else "lost"
        series = (m.get("event_ticker") or f.ticker).split("-")[0]

        if kind == "future":
            yes_mid = _now_mid(m)
            if yes_mid is not None and g.result == "open":
                g.kalshi_close = float(yes_mid if f.side == "yes" else 1 - yes_mid)
                g.fair, g.fair_source = g.kalshi_close, "Kalshi's price now"
                g.notes.append("Season-long bet: graded by how far the price has moved since you bought.")
            else:
                g.notes.append("Season-long bet that has settled: there's no single pre-game price to grade it on.")
            grades.append(g)
            continue

        legs = [leg.get("event_ticker") or (leg.get("market_ticker") or "").rsplit("-", 1)[0]
                for leg in (m.get("mve_selected_legs") or [])] if kind == "combo" else [m.get("event_ticker") or ""]
        starts = [(s, src, lg) for s, src, lg, _ in (_event_start(lk, e, events) for e in legs if e)]
        known = [x for x in starts if x[0] is not None]
        if not known or (kind == "combo" and len(known) < len(starts)):
            g.notes.append("Couldn't find when the game started, so there's no closing price to grade against.")
            grades.append(g)
            continue
        g.start, g.start_source, g.league = min(known, key=lambda x: x[0])
        if f.at >= g.start:
            g.notes.append("Placed after the game started: in-game prices move with the score, so it isn't graded.")
            grades.append(g)
            continue

        key = (f.ticker, int(g.start.timestamp()))
        if key not in closes:
            closes[key] = _closing(lk, series, f.ticker, g.start, f.at)
        mid, spread = closes[key]
        if mid is not None:
            g.kalshi_close = float(mid if f.side == "yes" else 1 - mid)
            if spread is not None and spread > WIDE_SPREAD:
                g.notes.append(f"Kalshi's buy and sell prices were {spread * 100:.0f}¢ apart at kickoff, "
                               "so its closing price is rough.")
        if kind == "game" and g.league and m.get("event_ticker"):
            siblings = events.get(m["event_ticker"], (None, "", "", []))[3]
            try:
                p_yes = lk.books_close(g.league, m, siblings)
            except Exception:
                p_yes = None
            if p_yes is not None:
                g.books_close = p_yes if f.side == "yes" else 1 - p_yes
        if g.books_close is not None:
            g.fair, g.fair_source = g.books_close, "Pinnacle's closing line"
        elif g.kalshi_close is not None:
            g.fair, g.fair_source = g.kalshi_close, "Kalshi's price at kickoff"
        else:
            g.notes.append("No trades on Kalshi before kickoff to read a closing price from.")
        grades.append(g)
    return Summary(grades)


def _now_mid(m: dict) -> Decimal | None:
    bid, ask = price_field(m, "yes_bid"), price_field(m, "yes_ask")
    if bid is not None and ask is not None and 0 < ask <= 1 and bid <= ask:
        return (bid + ask) / 2
    return None


def _closing(lk: Lookups, series: str, ticker: str, start: datetime, bought: datetime):
    """Kalshi's mid one minute before kickoff (1-minute candles), else the last hourly one before it."""
    end = int(start.timestamp())
    try:
        mid, spread = close_mid(lk.candles(series, ticker, end - 90 * 60, end, 1), start - timedelta(minutes=1))
    except Exception:
        mid = spread = None
    if mid is None:
        try:
            first = int(min(bought, start - timedelta(hours=6)).timestamp())
            mid, spread = close_mid(lk.candles(series, ticker, first, end, 60), start)
        except Exception:
            pass
    return mid, spread


# ---------------------------------------------------------------- sportsbook closing lines


class _Snap:
    def __init__(self, m: dict):
        self.ticker, self.event_ticker = m.get("ticker", ""), m.get("event_ticker", "")
        self.team = (m.get("yes_sub_title") or "").strip()


def books_close_lookup(fetch: Callable[[str], str]) -> Callable[[str, dict, list[dict]], float | None]:
    """Pinnacle-grade closing no-vig chance for a winner market: nflverse (NFL), football-data (soccer)."""
    from . import history, reference

    loaded: dict[str, object] = {}

    def source(league: str, when: datetime):
        key = f"{league}-{when.year if when.month >= 7 else when.year - 1}"
        if key not in loaded:
            try:
                if league == "NFL":
                    loaded[key] = history.nflverse_games(fetch(history.NFLVERSE_GAMES))
                else:
                    games = []
                    for url in reference.soccer_sources(league, when - timedelta(days=1), until=when):
                        games += reference.parse_football_data(fetch(url), uk_times=league not in reference.SOCCER_EXTRA)
                    loaded[key] = games
            except Exception:
                loaded[key] = []
        return loaded[key]

    def lookup(league: str, market: dict, siblings: list[dict]) -> float | None:
        series = (market.get("event_ticker") or "").split("-")[0]
        if not series.endswith("GAME") or (league != "NFL" and league not in reference.SOCCER_DIVISIONS
                                           and league not in reference.SOCCER_EXTRA):
            return None
        day, _ = parse_event_ticker(market.get("event_ticker") or "")
        if day is None:
            return None
        when = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        snaps = [_Snap(x) for x in (siblings or [market])]
        if league == "NFL":
            _, fair = history.nfl_match(snaps, source(league, when))
        else:
            _, fair = reference.name_match(snaps, source(league, when))
        hit = fair.get(market.get("ticker", ""))
        return hit[0] if hit else None

    return lookup
