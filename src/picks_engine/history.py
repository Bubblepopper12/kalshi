"""Kalshi price history for finished games, and two honest tests on it.

download():  every settled full-game winner market for a league since a date, with hourly
             price candles, written to a CSV (one row per market per hour).
analyze():   1. Longshot bias: are cheap contracts overpriced? Buckets the pre-game ask price
                and compares it with how often those contracts actually won.
             2. Kalshi vs. sportsbooks (NFL): using nflverse closing moneylines, would buying
                when Kalshi was cheaper than the books' fair chance have made money?

Runs where Kalshi is reachable (e.g. your own computer):  picks history download NFL
                                                          picks history analyze NFL
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
            markets = [m for m in client.markets(series_ticker=sr["ticker"], status="settled",
                                                 min_close_ts=int(since.timestamp()))
                       if (_ts(m.get("close_time")) or 0) >= since.timestamp() and m.get("result") in ("yes", "no")]
            progress(f"{sr['ticker']}: {len(markets)} finished markets since {since:%b %-d}")
            for i, m in enumerate(markets, 1):
                start = _ts(m.get("open_time")) or int((since - timedelta(days=7)).timestamp())
                end = _ts(m.get("close_time")) or int(datetime.now(timezone.utc).timestamp())
                try:
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
class Report:
    markets: int
    buckets: list[Bucket]
    strategy: list[str] = field(default_factory=list)

    def markdown(self, league: str) -> str:
        out = [f"# Kalshi {league} history test ({datetime.now():%b %-d, %Y})", "",
               f"{self.markets} finished winner markets, priced before each game.", "",
               "## 1. Are cheap contracts overpriced? (longshot bias)", "",
               "Buying at the pre-game ask price, including Kalshi's fee:", "",
               "| Price | Markets | Average price | Actually won | Return per bet |",
               "| --- | --- | --- | --- | --- |"]
        out += [b.line() for b in self.buckets]
        out += ["", "If cheap buckets win less often than their price, longshots are overpriced.", ""]
        if self.strategy:
            out += ["## 2. Buying when Kalshi was cheaper than the sportsbooks", ""] + self.strategy
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


def strategy_lines(snaps: list[Snapshot], fair: dict[str, tuple[float, str]], fee_rate: float = 0.07) -> list[str]:
    matched = [(s, fair[s.ticker][0]) for s in snaps if s.ticker in fair]
    if not matched:
        return ["No games matched the sportsbook closing lines (nflverse may not have this season's odds yet)."]
    lines = [f"{len(matched)} Kalshi prices matched with closing sportsbook lines.", ""]
    ll_k = ll_b = 0.0
    for s, f in matched:
        mid = float(s.ask if s.bid is None else (s.ask + s.bid) / 2)
        mid = min(max(mid, 0.01), 0.99)
        y = 1.0 if s.won else 0.0
        ll_k -= y * math.log(mid) + (1 - y) * math.log(1 - mid)
        ll_b -= y * math.log(f) + (1 - y) * math.log(1 - f)
    lines += [f"Prediction error (log loss, lower is better): Kalshi {ll_k / len(matched):.3f}, "
              f"sportsbooks {ll_b / len(matched):.3f}.", "",
              "| Rule | Bets | Won | Return per bet |", "| --- | --- | --- | --- |"]
    for edge in (0.0, 0.03, 0.05):
        n = wins = 0
        pnl = 0.0
        for s, f in matched:
            cost = float(s.ask) + fee_per_contract(float(s.ask), 10, fee_rate)
            if f - cost >= edge and not (edge > 0 and s.ask < Decimal("0.15") and f - cost < 0.08):
                n += 1
                wins += s.won
                pnl += (1 - cost) if s.won else -cost
        rule = "any" if edge == 0 else f"{edge * 100:.0f}+"
        lines.append(f"| Kalshi {rule} points cheaper than the books | {n} | {wins} | "
                     f"{(pnl / n * 100 if n else 0):+.1f}% |")
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


def analyze(path: Path, league: str, nflverse_csv: str | None = None, fee_rate: float = 0.07) -> Report:
    kickoffs, fair = {}, {}
    if league == "NFL" and nflverse_csv:
        prelim = load_snapshots(path)
        kickoffs, fair = nfl_match(prelim, nflverse_games(nflverse_csv))
    snaps = load_snapshots(path, kickoffs or None)
    report = Report(markets=len(snaps), buckets=longshot_buckets(snaps, fee_rate))
    if league == "NFL" and nflverse_csv:
        report.strategy = strategy_lines(snaps, fair, fee_rate) + [""] + timing_lines(path, kickoffs, fair, fee_rate)
    return report
