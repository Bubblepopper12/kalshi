"""Loading (and briefly caching) what the pages show: Kalshi games and sportsbook comparisons.

Caches live in memory for the life of a warm server instance:
  * Kalshi listings: 90 s, so prices on every page are fresh;
  * sportsbook odds: 10 min per league (they use the monthly quota), and
    "Refresh" can't refetch more than once every 2 minutes. The all-leagues view
    accepts odds up to 45 min old, only looks up leagues with games in the next
    3 days, and stops looking up new odds when the monthly quota runs low.
The comparison itself is recomputed on every page load from fresh Kalshi prices
and the cached odds, so a pick never rests on a stale Kalshi price.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

from ..config import Settings
from ..kalshi.client import KalshiReadOnlyClient
from ..kalshi.leagues import LEAGUES, game_series
from ..live.board import Game, games_from_events
from ..live.odds_api import DEFAULT_BOOKMAKERS, OddsAPIClient, OddsAPIError
from ..live.lines import Bet, grade_bet, model_for, price_markets, winner_no_bets
from ..live.picks import PicksResult, compare, find_game

SERIES_TTL = 600
EVENTS_TTL = 90
ODDS_TTL = 600
ODDS_MIN_REFRESH = 120
ALL_ODDS_TTL = 45 * 60
SOON_DAYS = 3
QUOTA_FLOOR = 25  # below this many lookups left, the all-leagues view only uses odds it already has
MAX_PARALLEL = 5

_series: dict[str, tuple[float, list[dict]]] = {}
_events: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_odds: dict[str, tuple[float, list[dict], int | None]] = {}
_quota: dict[str, int] = {}  # last known sportsbook lookups left this month


def clear_caches() -> None:
    _series.clear()
    _events.clear()
    _odds.clear()
    _quota.clear()


def odds_markets(league: str) -> str:
    """What to ask the sportsbook feed for. Spreads/totals let the bot price every Kalshi line, but each
    extra market counts as another request on the monthly plan; PICKS_LINES=0 turns them off."""
    if os.environ.get("PICKS_LINES", "1") == "0":
        return "h2h"
    return "h2h,totals" if LEAGUES[league].sport == "soccer" else "h2h,spreads,totals"


@dataclass
class AllPicks:
    """Picks across every league at once."""

    result: PicksResult
    left: int | None  # sportsbook lookups left this month
    oldest: float | None  # when the oldest odds used were fetched
    leagues: list[str] = field(default_factory=list)  # league codes compared
    quiet: list[str] = field(default_factory=list)  # league names with no Kalshi games in the next few days
    waiting: list[str] = field(default_factory=list)  # league names skipped to save sportsbook lookups
    failed: list[str] = field(default_factory=list)


@dataclass
class Loaded:
    games: list[Game]
    failed: list[str] = field(default_factory=list)  # league names that couldn't be loaded


@dataclass
class Sources:
    settings: Settings
    market_transport: httpx.BaseTransport | None = None
    odds_transport: httpx.BaseTransport | None = None
    clock: object = None  # optional () -> datetime (tests pin it)

    def kalshi(self) -> KalshiReadOnlyClient:
        # One retry at most: a page shouldn't hang on Kalshi's backoff.
        return KalshiReadOnlyClient(self.settings.kalshi_api_base, requests_per_second=20,
                                    transport=self.market_transport, max_retries=1)

    def now(self) -> datetime | None:
        return self.clock() if self.clock else None

    def compare_options(self) -> dict:
        s = self.settings
        return {"min_edge": s.picks_min_edge, "fee_rate": s.kalshi_fee_rate,
                "longshot_price": s.picks_longshot_price, "longshot_edge": s.picks_longshot_edge}

    # ------------------------------------------------------------ Kalshi

    def _sports_series(self, rc: KalshiReadOnlyClient) -> list[dict]:
        hit = _series.get("sports")
        if hit and time.time() - hit[0] < SERIES_TTL:
            return hit[1]
        data = rc.series(category="Sports")
        _series["sports"] = (time.time(), data)
        return data

    def events(self, league: str, kind: str) -> list[dict]:
        hit = _events.get((league, kind))
        if hit and time.time() - hit[0] < EVENTS_TTL:
            return hit[1]
        with self.kalshi() as rc:
            out: list[dict] = []
            for sr in game_series(LEAGUES[league], self._sports_series(rc), kind):
                out.extend(rc.events(sr["ticker"], status="open", with_nested_markets=True))
        _events[(league, kind)] = (time.time(), out)
        return out

    def games(self, leagues: list[str], kind: str) -> Loaded:
        """Fresh Kalshi games for several leagues (in parallel), with cached sportsbook numbers laid on top."""
        with self.kalshi() as rc:  # warm the shared series listing once, before the threads start
            self._sports_series(rc)

        def load(code: str):
            try:
                return code, games_from_events(self.events(code, kind), code, kind), None
            except httpx.HTTPError as exc:
                return code, [], exc

        loaded = Loaded([])
        with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL, len(leagues))) as pool:
            for code, games, err in pool.map(load, leagues):
                if err is not None:
                    loaded.failed.append(LEAGUES[code].name)
                    continue
                if kind == "moneyline" and code in _odds and time.time() - _odds[code][0] < ODDS_TTL:
                    lg = LEAGUES[code]
                    games = compare(games, _odds[code][1], three_way=lg.three_way, now=self.now(),
                                    **self.compare_options()).board
                loaded.games.extend(games)
        return loaded

    # ------------------------------------------------------------ comparison with sportsbooks

    def _odds_for(self, league: str, max_age: float) -> tuple[float, list[dict], int | None]:
        hit = _odds.get(league)
        now = time.time()
        if hit and now - hit[0] < max_age:
            return hit
        s = self.settings
        with OddsAPIClient(s.odds_api_key or "", s.odds_bookmakers or DEFAULT_BOOKMAKERS,
                           transport=self.odds_transport) as oc:
            odds = oc.moneylines(LEAGUES[league].odds_sport, odds_markets(league))
        hit = (now, odds.events, odds.requests_remaining)
        _odds[league] = hit
        if odds.requests_remaining is not None:
            _quota["left"] = odds.requests_remaining
        return hit

    def picks(self, league: str, refresh: bool = False) -> tuple[PicksResult, int | None, float | None]:
        """(result, sportsbook lookups left, when the odds were fetched) for one league."""
        lg = LEAGUES[league]
        games = games_from_events(self.events(league, "moneyline"), league, "moneyline")
        if not games:  # nothing on Kalshi: don't spend a sportsbook lookup, don't cache anything
            hit = _odds.get(league)
            return compare([], [], three_way=lg.three_way), (hit[2] if hit else None), None
        hit = self._odds_for(league, ODDS_MIN_REFRESH if refresh else ODDS_TTL)
        result = compare(games, hit[1], three_way=lg.three_way, now=self.now(), **self.compare_options())
        return result, hit[2], hit[0]

    def picks_all(self, refresh: bool = False) -> AllPicks:
        """Every league with Kalshi games in the next few days, compared with the sportsbooks."""
        with self.kalshi() as rc:
            self._sports_series(rc)
        today = (self.now() or datetime.now(timezone.utc)).date()
        soon = today + timedelta(days=SOON_DAYS)

        def load(code: str):
            try:
                games = games_from_events(self.events(code, "moneyline"), code, "moneyline")
            except httpx.HTTPError:
                return code, None
            return code, [g for g in games if g.day is None or today - timedelta(days=1) <= g.day <= soon]

        out = AllPicks(PicksResult([], [], [], 0, 0, []), None, None)
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
            loaded = list(pool.map(load, list(LEAGUES)))

        def compared(item):
            code, games = item
            if games is None:
                return code, None, "failed"
            if not games:
                return code, None, "no games"
            hit = _odds.get(code)
            max_age = ODDS_MIN_REFRESH if refresh else ALL_ODDS_TTL
            fresh = hit is not None and time.time() - hit[0] < max_age
            low = _quota.get("left", QUOTA_FLOOR) < QUOTA_FLOOR
            if not fresh and low:  # keep the last lookups for single-league pages; reuse older odds if any
                if hit is None:
                    return code, None, "quota"
            elif not fresh:
                try:
                    hit = self._odds_for(code, max_age)
                except (httpx.HTTPError, OddsAPIError):
                    return code, None, "failed"
            lg = LEAGUES[code]
            return code, (compare(games, hit[1], three_way=lg.three_way, now=self.now(), **self.compare_options()),
                          hit), ""

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
            for code, got, why in pool.map(compared, loaded):
                name = LEAGUES[code].name
                if got is None:
                    {"failed": out.failed, "quota": out.waiting, "no games": out.quiet}[why].append(name)
                    continue
                r, hit = got
                out.leagues.append(code)
                res = out.result
                res.picks += r.picks
                res.near += r.near
                res.board += r.board
                res.games_checked += r.games_checked
                res.games_matched += r.games_matched
                res.unmatched += r.unmatched
                res.in_progress += r.in_progress
                out.oldest = hit[0] if out.oldest is None else min(out.oldest, hit[0])
                if hit[2] is not None:
                    out.left = hit[2] if out.left is None else min(out.left, hit[2])
        out.result.picks.sort(key=lambda p: -p.edge)
        out.result.near.sort(key=lambda p: -p.edge)
        return out

    # ------------------------------------------------------------ spreads, totals, both teams score

    def line_bets(self, leagues: list[str]) -> tuple[list[Bet], list[Bet]]:
        """(picks, leans) among every spread / total / both-teams-to-score line and winner NO side, for games
        whose sportsbook odds are already loaded (by picks() or picks_all())."""
        now = self.now() or datetime.now(timezone.utc)
        min_edge = self.settings.picks_min_edge

        def one(code: str) -> list[Bet]:
            hit = _odds.get(code)
            if not hit:
                return []
            lg = LEAGUES[code]
            kinds = ["spread", "total"] + (["btts"] if lg.sport == "soccer" else [])
            try:
                winners = games_from_events(self.events(code, "moneyline"), code, "moneyline")
            except httpx.HTTPError:
                return []
            games: dict[str, tuple[dict, dict[str, str]]] = {}  # "26OCT18DALPHI" -> (sportsbook game, code sides)
            out: list[Bet] = []
            compared = compare(winners, hit[1], three_way=lg.three_way, now=now, **self.compare_options())
            for g in compared.board:  # the NO side of winner markets: "X doesn't win", "Not a draw"
                if g.matched and (g.starts is None or g.starts > now):
                    out += winner_no_bets(g, code, lg.sport, self.settings.kalshi_fee_rate)
            for g in winners:
                found = find_game(g, hit[1])
                if found and "-" in g.event_ticker:
                    oe, mapping = found
                    codes = {c.ticker.rsplit("-", 1)[-1]: mapping[c.name] for c in g.choices if c.name in mapping}
                    games[g.event_ticker.split("-", 1)[1]] = (oe, codes)
            models: dict[str, tuple] = {}
            for kind in kinds:
                try:
                    events = self.events(code, kind)
                except httpx.HTTPError:
                    continue
                for ev in events:
                    key = (ev.get("event_ticker") or "").split("-", 1)[-1]
                    if key not in games:
                        continue
                    oe, codes = games[key]
                    if key not in models:
                        models[key] = model_for(code, lg.sport, oe)
                    model, main = models[key]
                    for b in price_markets(ev.get("markets") or [], kind, code, lg.sport, oe, model, main,
                                           fee_rate=self.settings.kalshi_fee_rate, code_sides=codes):
                        if b.starts is None or b.starts > now:
                            out.append(b)
            graded = [(grade_bet(b, min_edge), b) for b in out]
            return [(g, b) for g, b in graded if g]

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
            bets = [x for chunk in pool.map(one, leagues) for x in chunk]
        # One per market: if both sides somehow qualify, keep the better one.
        best: dict[str, tuple[str, Bet]] = {}
        for g, b in bets:
            if b.ticker not in best or (g, b.edge) > (best[b.ticker][0], best[b.ticker][1].edge):
                best[b.ticker] = (g, b)
        picks = sorted((b for g, b in best.values() if g == "pick"), key=lambda b: -b.edge)
        leans = sorted((b for g, b in best.values() if g == "lean"), key=lambda b: -b.edge)
        return picks, leans
