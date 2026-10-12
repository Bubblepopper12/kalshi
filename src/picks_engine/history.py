"""Kalshi price history for finished games, and honest tests on it.

download():  every settled full-game winner market for a league since a date, with hourly
             price candles, written to a CSV (one row per market per hour).
analyze():   1. Longshot bias: are cheap contracts overpriced? Buckets the pre-game ask price
                and compares it with how often those contracts actually won.
             2. Kalshi vs. sportsbooks: using closing lines (nflverse for the NFL, football-data
                for soccer; see reference.py), would buying when Kalshi was cheaper than the
                books' fair chance have made money?
             3. Timing: was Kalshi further from the closing line earlier before kickoff?

Runs where Kalshi is reachable (your computer, or GitHub's servers):  picks research
"""

from __future__ import annotations

import csv
import io
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import httpx

from .kalshi.classify import parse_event_ticker
from .kalshi.client import KalshiReadOnlyClient
from .kalshi.leagues import LEAGUES, game_series
from .pricing.devig import devig
from .pricing.fees import fee_per_contract
from .reference import RefGame, name_match

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover - no tz database
    _ET = timezone(timedelta(hours=-4))

NFLVERSE_GAMES = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
COLUMNS = ["league", "series", "event_ticker", "ticker", "team", "result", "expected_end", "ts",
           "yes_bid", "yes_ask", "last_price", "volume"]
PREGAME_HOURS = 4  # without a known kickoff, "pre-game" = last candle 4h before the expected end
# Kalshi team codes that differ from nflverse's.
NFL_CODES = {"LAR": "LA", "JAC": "JAX", "WSH": "WAS", "LVR": "LV", "KCC": "KC", "SFO": "SF",
             "TBB": "TB", "NOS": "NO", "GBP": "GB", "NEP": "NE"}


def _ts(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _close(candle: dict, name: str) -> Decimal | None:
    """Closing value of one price series in a candle, in dollars.

    Kalshi nests them ({"yes_ask": {"close": 55}} in cents, or {"close_dollars": "0.5500"});
    flat fields ("yes_ask_close" in cents, "yes_ask_close_dollars") are accepted too.
    """
    part = candle.get(name)
    if isinstance(part, dict):
        if part.get("close_dollars") not in (None, ""):
            return Decimal(str(part["close_dollars"]))
        if part.get("close") not in (None, ""):
            return Decimal(str(part["close"])) / 100
    if candle.get(f"{name}_close_dollars") not in (None, ""):
        return Decimal(str(candle[f"{name}_close_dollars"]))
    if candle.get(f"{name}_close") not in (None, ""):
        return Decimal(str(candle[f"{name}_close"])) / 100
    return None


# ---------------------------------------------------------------- download


def download(client: KalshiReadOnlyClient, league: str, since: datetime, out: Path,
             period_minutes: int = 60, progress=print) -> int:
    """Write hourly price history of every settled winner market since `since`. Returns rows written."""
    lg = LEAGUES[league]
    progress(f"Asking Kalshi for {lg.name} game markets...")
    series = game_series(lg, client.series(category="Sports"), "moneyline")
    if not series:
        raise SystemExit(f"Kalshi lists no game-winner series for {lg.name}.")
    progress(f"Found {', '.join(s['ticker'] for s in series)}. Listing finished games since {since:%b %-d}...")
    rows = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, COLUMNS)
        w.writeheader()
        for sr in series:
            wanted = lambda m: ((_ts(m.get("close_time")) or 0) >= since.timestamp()  # noqa: E731
                                and m.get("result") in ("yes", "no"))
            markets = [m for m in client.markets(series_ticker=sr["ticker"], status="settled",
                                                 min_close_ts=int(since.timestamp())) if wanted(m)]
            seen = {m["ticker"] for m in markets}
            try:  # older games live under Kalshi's historical endpoints
                old = [dict(m, _historical=True) for m in client.historical_markets(sr["ticker"])
                       if wanted(m) and m.get("ticker") not in seen]
            except httpx.HTTPStatusError:
                old = []
            markets += old
            progress(f"{sr['ticker']}: {len(markets)} finished markets since {since:%b %-d}"
                     + (f" ({len(old)} from Kalshi's archive)" if old else ""))
            for i, m in enumerate(markets, 1):
                start = _ts(m.get("open_time")) or int((since - timedelta(days=7)).timestamp())
                end = _ts(m.get("close_time")) or int(datetime.now(timezone.utc).timestamp())
                try:
                    if m.get("_historical"):
                        candles = client.historical_candlesticks(m["ticker"], start, end, period_minutes)
                    else:
                        candles = client.candlesticks(sr["ticker"], m["ticker"], start, end, period_minutes)
                except httpx.HTTPStatusError as exc:
                    progress(f"  skipped {m['ticker']}: Kalshi returned {exc.response.status_code}")
                    continue
                for c in candles:
                    ask, bid = _close(c, "yes_ask"), _close(c, "yes_bid")
                    w.writerow({"league": league, "series": sr["ticker"], "event_ticker": m.get("event_ticker"),
                                "ticker": m["ticker"], "team": m.get("yes_sub_title") or "", "result": m["result"],
                                "expected_end": m.get("expected_expiration_time") or m.get("close_time") or "",
                                "ts": c.get("end_period_ts"), "yes_bid": bid, "yes_ask": ask,
                                "last_price": _close(c, "price"), "volume": c.get("volume")})
                    rows += 1
                if i % 10 == 0 or i == len(markets):
                    progress(f"  {i}/{len(markets)} markets downloaded")
    return rows


# ---------------------------------------------------------------- analysis


@dataclass
class Snapshot:
    ticker: str
    event_ticker: str
    team: str
    won: bool
    ask: Decimal
    bid: Decimal | None
    ts: int


@dataclass
class Bucket:
    low: int
    high: int
    n: int = 0
    price_sum: float = 0.0
    wins: int = 0
    pnl: float = 0.0

    def line(self) -> str:
        if not self.n:
            return f"| {self.low}–{self.high}¢ | 0 | | | |"
        avg = self.price_sum / self.n
        return (f"| {self.low}–{self.high}¢ | {self.n} | {avg * 100:.0f}% | {self.wins / self.n * 100:.0f}% | "
                f"{self.pnl / self.n * 100:+.1f}% |")


@dataclass
class Rule:
    label: str
    bets: int
    wins: int
    pnl: float  # dollars per $1 contract, summed

    @property
    def per_bet(self) -> float:
        return self.pnl / self.bets if self.bets else 0.0


@dataclass
class Comparison:
    """Kalshi's pre-game prices next to the sportsbooks' closing no-vig chances."""

    matched: int
    loss_kalshi: float  # log loss, lower = better predictions
    loss_books: float
    rules: list[Rule]

    def rule(self, edge_points: int) -> Rule:
        return self.rules[{0: 0, 3: 1, 5: 2}[edge_points]]


@dataclass
class Report:
    markets: int
    buckets: list[Bucket]
    strategy: list[str] = field(default_factory=list)
    games: int = 0
    comparison: Comparison | None = None
    source: str = ""  # where the closing lines came from, "" if none

    def longshots(self, below_cents: int = 20) -> Rule:
        bs = [b for b in self.buckets if b.high <= below_cents]
        return Rule(f"under {below_cents}¢", sum(b.n for b in bs), sum(b.wins for b in bs), sum(b.pnl for b in bs))

    def favorites(self, from_cents: int = 70) -> Rule:
        bs = [b for b in self.buckets if b.low >= from_cents]
        return Rule(f"{from_cents}¢ and up", sum(b.n for b in bs), sum(b.wins for b in bs), sum(b.pnl for b in bs))

    def markdown(self, league: str) -> str:
        name = LEAGUES[league].name if league in LEAGUES else league
        out = [f"# Kalshi {name} history test ({datetime.now():%b %-d, %Y})", "",
               f"{self.markets} finished winner markets, priced before each game.", "",
               "## 1. Are cheap contracts overpriced? (longshot bias)", "",
               "Buying at the pre-game ask price, including Kalshi's fee:", "",
               "| Price | Markets | Average price | Actually won | Return per bet |",
               "| --- | --- | --- | --- | --- |"]
        out += [b.line() for b in self.buckets]
        out += ["", "If cheap buckets win less often than their price, longshots are overpriced.", ""]
        if self.strategy:
            out += ["## 2. Buying when Kalshi was cheaper than the sportsbooks", ""]
            if self.source:
                out += [f"Closing lines from {self.source}.", ""]
            out += self.strategy
        else:
            out += ["## 2. Kalshi vs. the sportsbooks", "",
                    "Skipped: there's no free source of closing sportsbook lines for this league.", ""]
        return "\n".join(out)


def load_snapshots(path: Path, kickoffs: dict[str, int] | None = None, hours_before: float = 1.0) -> list[Snapshot]:
    """One pre-game price per market: the last candle before kickoff - hours_before (or a 4h fallback)."""
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    with path.open() as fh:
        for r in csv.DictReader(fh):
            if r["yes_ask"] not in ("", "None"):
                by_ticker[r["ticker"]].append(r)
    snaps = []
    for ticker, rows in by_ticker.items():
        r0 = rows[0]
        cutoff = None
        if kickoffs and r0["event_ticker"] in kickoffs:
            cutoff = kickoffs[r0["event_ticker"]] - hours_before * 3600
        elif _ts(r0["expected_end"]):
            cutoff = _ts(r0["expected_end"]) - PREGAME_HOURS * 3600
        if cutoff is None:
            continue
        before = [r for r in rows if r["ts"] and int(r["ts"]) <= cutoff]
        if not before:
            continue
        last = max(before, key=lambda r: int(r["ts"]))
        ask = Decimal(last["yes_ask"])
        if not 0 < ask < 1:
            continue
        bid = Decimal(last["yes_bid"]) if last["yes_bid"] not in ("", "None") else None
        snaps.append(Snapshot(ticker, r0["event_ticker"], r0["team"], r0["result"] == "yes", ask, bid, int(last["ts"])))
    return snaps


def longshot_buckets(snaps: list[Snapshot], fee_rate: float = 0.07) -> list[Bucket]:
    buckets = [Bucket(lo, lo + 10) for lo in range(0, 100, 10)]
    for s in snaps:
        b = buckets[min(int(s.ask * 100) // 10, 9)]
        cost = float(s.ask) + fee_per_contract(float(s.ask), 10, fee_rate)
        b.n += 1
        b.price_sum += float(s.ask)
        b.wins += s.won
        b.pnl += (1 - cost) if s.won else -cost
    return buckets


# ---------------------------------------------------------------- NFL: compare with nflverse closing lines


def nflverse_games(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def _code(c: str) -> str:
    return NFL_CODES.get(c.upper(), c.upper())


def _kickoff_utc(gameday: str, gametime: str) -> int | None:
    """nflverse kickoff (US Eastern wall clock) as a UTC timestamp, daylight saving included."""
    try:
        local = datetime.fromisoformat(f"{gameday}T{gametime or '13:00'}").replace(tzinfo=_ET)
    except ValueError:
        return None
    return int(local.timestamp())


def nfl_match(snaps: list[Snapshot], games: list[dict]) -> tuple[dict[str, int], dict[str, tuple[float, str]]]:
    """(kickoff time per Kalshi event, (book fair chance, nflverse game id) per Kalshi market)."""
    by_day: dict[str, list[dict]] = defaultdict(list)
    for g in games:
        by_day[g["gameday"]].append(g)
    kickoffs: dict[str, int] = {}
    fair: dict[str, tuple[float, str]] = {}
    for s in snaps:
        day, teams = parse_event_ticker(s.event_ticker)
        raw = s.ticker.rsplit("-", 1)[-1].upper()
        if not day or not teams or raw not in teams:
            continue
        team, opp = _code(raw), _code(teams.replace(raw, "", 1))
        g = next((g for d in (day, day - timedelta(days=1), day + timedelta(days=1))
                  for g in by_day.get(d.isoformat(), [])
                  if {_code(g["home_team"]), _code(g["away_team"])} == {team, opp}), None)
        if g is None:
            continue
        ko = _kickoff_utc(g["gameday"], g.get("gametime", ""))
        if ko:
            kickoffs[s.event_ticker] = ko
        if g.get("home_moneyline") not in (None, "", "NA") and g.get("away_moneyline") not in (None, "", "NA"):
            home, away = devig([float(g["home_moneyline"]), float(g["away_moneyline"])])
            fair[s.ticker] = (home if team == _code(g["home_team"]) else away, g["game_id"])
    return kickoffs, fair


def compare_with_books(snaps: list[Snapshot], fair: dict[str, tuple[float, str]],
                       fee_rate: float = 0.07) -> Comparison | None:
    matched = [(s, fair[s.ticker][0]) for s in snaps if s.ticker in fair]
    if not matched:
        return None
    ll_k = ll_b = 0.0
    for s, f in matched:
        mid = float(s.ask if s.bid is None else (s.ask + s.bid) / 2)
        mid = min(max(mid, 0.01), 0.99)
        f = min(max(f, 0.001), 0.999)
        y = 1.0 if s.won else 0.0
        ll_k -= y * math.log(mid) + (1 - y) * math.log(1 - mid)
        ll_b -= y * math.log(f) + (1 - y) * math.log(1 - f)
    rules = []
    for edge in (0.0, 0.03, 0.05):
        n = wins = 0
        pnl = 0.0
        for s, f in matched:
            cost = float(s.ask) + fee_per_contract(float(s.ask), 10, fee_rate)
            if f - cost >= edge and not (edge > 0 and s.ask < Decimal("0.15") and f - cost < 0.08):
                n += 1
                wins += s.won
                pnl += (1 - cost) if s.won else -cost
        rules.append(Rule("any" if edge == 0 else f"{edge * 100:.0f}+", n, wins, pnl))
    return Comparison(len(matched), ll_k / len(matched), ll_b / len(matched), rules)


def strategy_lines(snaps: list[Snapshot], fair: dict[str, tuple[float, str]], fee_rate: float = 0.07,
                   comparison: Comparison | None = None) -> list[str]:
    c = comparison or compare_with_books(snaps, fair, fee_rate)
    if c is None:
        return ["No games matched the sportsbook closing lines (the source may not have this season yet)."]
    lines = [f"{c.matched} Kalshi prices matched with closing sportsbook lines.", "",
             f"Prediction error (log loss, lower is better): Kalshi {c.loss_kalshi:.3f}, "
             f"sportsbooks {c.loss_books:.3f}.", "",
             "| Rule | Bets | Won | Return per bet |", "| --- | --- | --- | --- |"]
    for r in c.rules:
        lines.append(f"| Kalshi {r.label} points cheaper than the books | {r.bets} | {r.wins} | "
                     f"{r.per_bet * 100:+.1f}% |")
    lines += ["", "Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof."]
    return lines


TIMING_HOURS = (72, 48, 24, 6, 1)


def timing_lines(path: Path, kickoffs: dict[str, int], fair: dict[str, tuple[float, str]],
                 fee_rate: float = 0.07) -> list[str]:
    """How far Kalshi was from where the sportsbooks closed, at several times before kickoff.

    Uses the closing line, which you wouldn't have known yet at those times: it shows whether
    big gaps existed early (Kalshi lagging), not a ready-made strategy.
    """
    lines = ["## 3. Does Kalshi lag earlier in the week?", "",
             "Kalshi's price at each time vs. where the sportsbooks *closed* (which you couldn't know yet).",
             "A big early gap that buying would have profited from means Kalshi lags the books.", "",
             "| Before kickoff | Prices | Avg gap | Kalshi 3+ pts below close | Won | Return per bet |",
             "| --- | --- | --- | --- | --- | --- |"]
    for hours in TIMING_HOURS:
        snaps = [s for s in load_snapshots(path, kickoffs, hours_before=hours)
                 if s.ticker in fair and s.event_ticker in kickoffs and kickoffs[s.event_ticker] - s.ts <= (hours + 6) * 3600]
        if not snaps:
            lines.append(f"| {hours} h | 0 | | | | |")
            continue
        gaps, n, wins, pnl = [], 0, 0, 0.0
        for s in snaps:
            f = fair[s.ticker][0]
            mid = float(s.ask if s.bid is None else (s.ask + s.bid) / 2)
            gaps.append(abs(f - mid))
            cost = float(s.ask) + fee_per_contract(float(s.ask), 10, fee_rate)
            if f - cost >= 0.03:
                n += 1
                wins += s.won
                pnl += (1 - cost) if s.won else -cost
        avg_gap = sum(gaps) / len(gaps) * 100
        lines.append(f"| {hours} h | {len(snaps)} | {avg_gap:.1f} pts | {n} | {wins} | "
                     f"{(pnl / n * 100 if n else 0):+.1f}% |")
    return lines + [""]


def analyze(path: Path, league: str, nflverse_csv: str | None = None, fee_rate: float = 0.07,
            reference: list[RefGame] | None = None, source: str = "") -> Report:
    """Run the tests. Closing lines come from nflverse (NFL) or `reference` (other leagues)."""
    kickoffs, fair = {}, {}
    if league == "NFL" and nflverse_csv:
        kickoffs, fair = nfl_match(load_snapshots(path), nflverse_games(nflverse_csv))
        source = source or "nflverse"
    elif reference is not None:
        kickoffs, fair = name_match(load_snapshots(path), reference)
    snaps = load_snapshots(path, kickoffs or None)
    report = Report(markets=len(snaps), buckets=longshot_buckets(snaps, fee_rate),
                    games=len({s.event_ticker for s in snaps}))
    if (league == "NFL" and nflverse_csv) or reference is not None:
        report.source = source
        report.comparison = compare_with_books(snaps, fair, fee_rate)
        report.strategy = strategy_lines(snaps, fair, fee_rate, report.comparison)
        if kickoffs and report.comparison:
            report.strategy += [""] + timing_lines(path, kickoffs, fair, fee_rate)
    return report
