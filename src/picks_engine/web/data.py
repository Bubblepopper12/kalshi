"""Loading (and briefly caching) what the pages show: Kalshi games and sportsbook comparisons.

Caches live in memory for the life of a warm server instance:
  * Kalshi listings: 90 s, so prices on every page are fresh;
  * sportsbook odds: 10 min per league (they use the monthly quota), and
    "Refresh" can't refetch more than once every 2 minutes.
The comparison itself is recomputed on every page load from fresh Kalshi prices
and the cached odds, so a pick never rests on a stale Kalshi price.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from ..config import Settings
from ..kalshi.client import KalshiReadOnlyClient
from ..kalshi.leagues import LEAGUES, game_series
from ..live.board import Game, games_from_events
from ..live.odds_api import DEFAULT_BOOKMAKERS, OddsAPIClient
from ..live.picks import PicksResult, compare

SERIES_TTL = 600
EVENTS_TTL = 90
ODDS_TTL = 600
ODDS_MIN_REFRESH = 120
MAX_PARALLEL = 5

_series: dict[str, tuple[float, list[dict]]] = {}
_events: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_odds: dict[str, tuple[float, list[dict], int | None]] = {}


def clear_caches() -> None:
    _series.clear()
    _events.clear()
    _odds.clear()


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

    def picks(self, league: str, refresh: bool = False) -> tuple[PicksResult, int | None, float | None]:
        """(result, sportsbook lookups left, when the odds were fetched) for one league."""
        s, lg = self.settings, LEAGUES[league]
        games = games_from_events(self.events(league, "moneyline"), league, "moneyline")
        if not games:  # nothing on Kalshi: don't spend a sportsbook lookup, don't cache anything
            hit = _odds.get(league)
            return compare([], [], three_way=lg.three_way), (hit[2] if hit else None), None
        now = time.time()
        hit = _odds.get(league)
        fresh = hit and (now - hit[0] < (ODDS_MIN_REFRESH if refresh else ODDS_TTL))
        if not fresh:
            with OddsAPIClient(s.odds_api_key or "", s.odds_bookmakers or DEFAULT_BOOKMAKERS,
                               transport=self.odds_transport) as oc:
                odds = oc.moneylines(lg.odds_sport)
            hit = (now, odds.events, odds.requests_remaining)
            _odds[league] = hit
        result = compare(games, hit[1], three_way=lg.three_way, now=self.now(), **self.compare_options())
        return result, hit[2], hit[0]
