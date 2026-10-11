"""Picks: where Kalshi sells an outcome for less than the sportsbooks think it's worth.

For each Kalshi full-game winner market:
  1. find the same game in the sportsbook feed (date + both team names),
  2. remove each book's margin (de-vig) and take the median fair chance,
  3. compare with the Kalshi YES ask plus Kalshi's fee,
  4. edge = fair chance - cost.
Every matched game keeps its numbers (the board); outcomes with edge >= min_edge,
at least two books and a game that hasn't started become picks. Each pick gets a
strength label and plain-language cautions. Sizing is quarter-Kelly on the cash
balance, capped by the per-bet limit.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal

from ..pricing.devig import devig
from ..pricing.fees import fee_per_contract
from ..pricing.kelly import stake_fraction
from .board import Choice, Game, games_from_events
from .teams import assign, is_draw

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    _ET = timezone.utc

SHARP_BOOKS = ("pinnacle",)
STALE_AFTER = timedelta(minutes=60)
THIN_GAP = Decimal("0.10")


@dataclass
class BookView:
    fair: float  # median de-vigged chance across books
    books: list[str]  # bookmaker names used
    low: float
    high: float
    updated: datetime | None
    pinnacle: float | None = None


@dataclass
class Pick:
    game: Game
    choice: Choice
    strength: str = "Good"  # Strong | Good | Close call
    notes: list[str] = field(default_factory=list)
    odds_updated: datetime | None = None
    contracts: int = 0
    stake: Decimal = Decimal(0)

    # Shortcuts used by pages and tests
    @property
    def ticker(self) -> str:
        return self.choice.ticker

    @property
    def outcome(self) -> str:
        return self.choice.statement

    @property
    def game_title(self) -> str:
        return self.game.title

    @property
    def edge(self) -> float:
        return self.choice.edge or 0.0

    @property
    def fair(self) -> float:
        return self.choice.book or 0.0

    @property
    def ask(self) -> Decimal:
        return self.choice.yes_ask or Decimal(0)

    @property
    def fee(self) -> Decimal:
        return self.choice.fee or Decimal(0)

    @property
    def cost(self) -> Decimal:
        return self.ask + self.fee

    @property
    def books(self) -> list[str]:
        return self.choice.books


@dataclass
class PicksResult:
    picks: list[Pick]  # edge >= min_edge, best first
    near: list[Pick]  # 0 < edge < min_edge
    board: list[Game]  # every game still to be played, matched or not
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
    """Outcome ('home'/'away'/'draw') -> consensus across bookmakers."""
    home, away = odds_event.get("home_team", ""), odds_event.get("away_team", "")
    per: dict[str, list[float]] = {"home": [], "away": [], "draw": []}
    sharp: dict[str, float] = {}
    names: list[str] = []
    latest: datetime | None = None
    wanted = ["home", "away", "draw"] if three_way else ["home", "away"]
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
        if any(k not in prices for k in wanted):
            continue
        try:
            fair = devig([prices[k] for k in wanted])
        except ValueError:
            continue
        for k, p in zip(wanted, fair):
            per[k].append(p)
            if (bk.get("key") or "").lower() in SHARP_BOOKS:
                sharp[k] = p
        names.append(bk.get("title") or bk.get("key") or "?")
        upd = _parse(market.get("last_update") or bk.get("last_update"))
        if upd and (latest is None or upd > latest):
            latest = upd
    return {k: BookView(statistics.median(v), names, min(v), max(v), latest, sharp.get(k))
            for k, v in per.items() if v}


def _same_day(kalshi_day: date | None, commence: datetime | None) -> bool:
    if kalshi_day is None or commence is None:
        return True
    return abs((commence.astimezone(_ET).date() - kalshi_day).days) <= 1


def find_game(game: Game, odds_events: list[dict]) -> tuple[dict, dict[str, str]] | None:
    names = [c.name for c in game.choices]
    found = []
    for oe in odds_events:
        if not _same_day(game.day, _parse(oe.get("commence_time"))):
            continue
        mapping = assign(names, oe.get("home_team", ""), oe.get("away_team", ""))
        if mapping:
            found.append((oe, mapping))
    return found[0] if len(found) == 1 else None


def judge(pick: Pick, min_edge: float, now: datetime) -> None:
    """Strength label and plain-language cautions."""
    c, g = pick.choice, pick.game
    cost = float(c.cost or 0)
    sharp_ok = c.pinnacle is None or c.pinnacle - cost >= 0.01
    if pick.edge >= max(min_edge, 0.05) and len(c.books) >= 3 and sharp_ok and not g.stretched:
        pick.strength = "Strong"
    elif pick.edge >= min_edge:
        pick.strength = "Good"
    else:
        pick.strength = "Close call"
    if c.pinnacle is not None and c.pinnacle - cost < 0:
        pick.notes.append("Pinnacle, the sharpest sportsbook, doesn't agree this is cheap.")
    if len(c.books) < 3:
        pick.notes.append(f"Only {len(c.books)} sportsbooks priced this game.")
    if c.book_low is not None and c.book_high is not None and c.book_high - c.book_low > 0.06:
        pick.notes.append("The sportsbooks disagree with each other by more than 6 points.")
    if c.gap is not None and c.gap > THIN_GAP:
        pick.notes.append("Few people are trading this on Kalshi yet (big gap between buy and sell prices).")
    if pick.odds_updated and now - pick.odds_updated > STALE_AFTER:
        pick.notes.append("Sportsbook prices are over an hour old.")


def compare(games: list[Game], odds_events: list[dict], *, three_way: bool, min_edge: float = 0.03,
            fee_rate: float = 0.07, fee_contracts: int = 10, now: datetime | None = None) -> PicksResult:
    now = now or datetime.now(timezone.utc)
    picks, near, board, unmatched = [], [], [], []
    checked = matched = 0
    for g in games:
        checked += 1
        found = find_game(g, odds_events)
        if found is None:
            unmatched.append(g.title or g.event_ticker)
            board.append(g)
            continue
        oe, mapping = found
        starts = _parse(oe.get("commence_time"))
        if starts and starts <= now:
            continue  # already started: in-game prices are a different thing
        matched += 1
        g.starts, g.matched = starts, True
        g.names = [oe.get("home_team", ""), oe.get("away_team", "")]
        views = book_views(oe, three_way)
        for c in g.choices:
            side = "draw" if is_draw(c.name) else mapping.get(c.name)
            view = views.get(side or "")
            if view is None or not c.buyable or len(view.books) < 2:
                continue
            c.fee = Decimal(str(fee_per_contract(float(c.yes_ask), fee_contracts, fee_rate))).quantize(Decimal("0.0001"))
            c.book, c.books, c.book_low, c.book_high, c.pinnacle = view.fair, view.books, view.low, view.high, view.pinnacle
            c.edge = view.fair - float(c.yes_ask + c.fee)
            if c.edge > 0:
                p = Pick(game=g, choice=c, odds_updated=view.updated)
                judge(p, min_edge, now)
                (picks if c.edge >= min_edge else near).append(p)
        board.append(g)
    picks.sort(key=lambda p: p.edge, reverse=True)
    near.sort(key=lambda p: p.edge, reverse=True)
    return PicksResult(picks, near, board, checked, matched, unmatched)


def build_picks(kalshi_events: list[dict], odds_events: list[dict], *, three_way: bool, league: str = "",
                min_edge: float = 0.03, fee_rate: float = 0.07, fee_contracts: int = 10,
                now: datetime | None = None) -> PicksResult:
    games = games_from_events(kalshi_events, league, "moneyline")
    return compare(games, odds_events, three_way=three_way, min_edge=min_edge, fee_rate=fee_rate,
                   fee_contracts=fee_contracts, now=now)


def size(pick: Pick, cash: Decimal | None, max_order: float, kelly_fraction: float = 0.25) -> None:
    """Suggested contracts and stake: quarter-Kelly of cash, capped at the per-bet limit."""
    cost = pick.cost
    if cost <= 0:
        pick.contracts, pick.stake = 0, Decimal(0)
        return
    frac = stake_fraction(pick.fair, float(cost), kelly_fraction=kelly_fraction, cap=1.0)
    budget = Decimal(str(max_order))
    if cash is not None:
        budget = min(budget, cash * Decimal(str(frac)), cash)
    pick.contracts = max(int((budget / cost).to_integral_value(rounding=ROUND_DOWN)), 0)
    pick.stake = (cost * pick.contracts).quantize(Decimal("0.01"))
