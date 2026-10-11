"""Loading (and briefly caching) what the pages show: Kalshi games and sportsbook comparisons.

Caches live in memory for the life of a warm server instance. Kalshi listings
are cheap to refetch (90 s); sportsbook odds use the monthly quota, so a
league's comparison is reused for 10 minutes and "Refresh" can't refetch more
than once every 2 minutes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from ..config import Settings
from ..kalshi.client import KalshiReadOnlyClient
from ..kalshi.leagues import LEAGUES, game_series
from ..live.board import Game, games_from_events
from ..live.odds_api import DEFAULT_BOOKMAKERS, OddsAPIClient
from ..live.picks import PicksResult, compare

SERIES_TTL = 600
EVENTS_TTL = 90
PICKS_TTL = 600
PICKS_MIN_REFRESH = 120

_series: dict[str, tuple[float, list[dict]]] = {}
_events: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_picks: dict[str, tuple[float, PicksResult, int | None]] = {}


def clear_caches() -> None:
    _series.clear()
    _events.clear()
    _picks.clear()


@dataclass
class Sources:
    settings: Settings
    market_transport: httpx.BaseTransport | None = None
    odds_transport: httpx.BaseTransport | None = None
    clock: object = None  # optional () -> datetime, for tests

    def kalshi(self) -> KalshiReadOnlyClient:
        return KalshiReadOnlyClient(self.settings.kalshi_api_base, requests_per_second=20,
                                    transport=self.market_transport)

    # ------------------------------------------------------------ Kalshi

    def sports_series(self, rc: KalshiReadOnlyClient) -> list[dict]:
        hit = _series.get("sports")
        if hit and time.time() - hit[0] < SERIES_TTL:
            return hit[1]
        data = rc.series(category="Sports")
        _series["sports"] = (time.time(), data)
        return data

    def events(self, league: str, kind: str, rc: KalshiReadOnlyClient | None = None) -> list[dict]:
        hit = _events.get((league, kind))
        if hit and time.time() - hit[0] < EVENTS_TTL:
            return hit[1]
        own = rc is None
        rc = rc or self.kalshi()
        try:
            out: list[dict] = []
            for sr in game_series(LEAGUES[league], self.sports_series(rc), kind):
                out.extend(rc.events(sr["ticker"], status="open", with_nested_markets=True))
        finally:
            if own:
                rc.close()
        _events[(league, kind)] = (time.time(), out)
        return out

    def games(self, leagues: list[str], kind: str) -> list[Game]:
        """Games for several leagues; winner markets reuse the sportsbook comparison when one is cached."""
        games: list[Game] = []
        with self.kalshi() as rc:
            for code in leagues:
                cached = _picks.get(code)
                if kind == "moneyline" and cached and time.time() - cached[0] < PICKS_TTL:
                    games.extend(cached[1].board)
                else:
                    games.extend(games_from_events(self.events(code, kind, rc), code, kind))
        return games

    # ------------------------------------------------------------ comparison with sportsbooks

    def picks(self, league: str, refresh: bool = False) -> tuple[PicksResult, int | None, float]:
        """(result, sportsbook requests left, fetched at) for one league."""
        now = time.time()
        hit = _picks.get(league)
        if hit and (now - hit[0] < PICKS_TTL and not refresh or refresh and now - hit[0] < PICKS_MIN_REFRESH):
            return hit[1], hit[2], hit[0]
        s, lg = self.settings, LEAGUES[league]
        games = games_from_events(self.events(league, "moneyline"), league, "moneyline")
        left = hit[2] if hit else None
        if games:
            with OddsAPIClient(s.odds_api_key or "", s.odds_bookmakers or DEFAULT_BOOKMAKERS,
                               transport=self.odds_transport) as oc:
                odds = oc.moneylines(lg.odds_sport)
            left = odds.requests_remaining
            result = compare(games, odds.events, three_way=lg.three_way, min_edge=s.picks_min_edge,
                             fee_rate=s.kalshi_fee_rate, now=self.clock() if self.clock else None)
        else:
            result = compare([], [], three_way=lg.three_way)
        _picks[league] = (now, result, left)
        return result, left, now
