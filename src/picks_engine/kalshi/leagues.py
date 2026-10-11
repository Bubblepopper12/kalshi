"""League definitions and how to find each league's series in Kalshi's live listings.

Kalshi's soccer depth varies by league and new series appear without notice, so
nothing here hard-codes series tickers. Each run reads /series and keeps the
ones whose ticker prefix or title matches the league.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class League:
    code: str
    name: str
    sport: str  # football | basketball | soccer
    priority: int
    season: str
    ticker_prefixes: tuple[str, ...]
    title_pattern: str  # regex, case-insensitive, matched only for Sports-category series
    exclude_pattern: str | None = None
    odds_sport: str = ""  # The Odds API sport key, used for sportsbook prices
    three_way: bool = False  # soccer: home / draw / away

    def matches(self, series: dict) -> bool:
        ticker = (series.get("ticker") or "").upper()
        title = series.get("title") or ""
        if self.exclude_pattern and re.search(self.exclude_pattern, f"{ticker} {title}", re.I):
            return False
        if ticker.startswith(self.ticker_prefixes):
            return True
        category = (series.get("category") or "").lower()
        if category and category != "sports":
            return False
        return re.search(self.title_pattern, title, re.I) is not None


LEAGUES: dict[str, League] = {
    lg.code: lg
    for lg in [
        League(
            "NFL", "NFL", "football", 1, "Sep–Feb",
            ("KXNFL", "KXMVENFL", "KXSB"),
            r"\bNFL\b|\bpro football\b|\bsuper bowl\b",
            odds_sport="americanfootball_nfl",
        ),
        League(
            "CFB", "College football / CFP", "football", 1, "Aug–Jan",
            ("KXNCAAF", "KXCFB", "KXCFP", "KXMVENCAAF", "KXHEISMAN"),
            r"\bcollege football\b|\bNCAAF\b|\bCFP\b|\bheisman\b",
            odds_sport="americanfootball_ncaaf",
        ),
        League(
            "NBA", "NBA", "basketball", 1, "Oct–Jun",
            ("KXNBA", "KXMVENBA"),
            r"(?<!W)\bNBA\b|\bpro basketball\b",
            odds_sport="basketball_nba",
        ),
        League(
            "EPL", "Premier League", "soccer", 2, "Aug–May",
            ("KXEPL", "KXPREMIERLEAGUE"),
            r"\bpremier league\b|\bEPL\b",
            odds_sport="soccer_epl", three_way=True,
        ),
        League(
            "UCL", "Champions League", "soccer", 2, "Sep–May",
            ("KXUCL", "KXCHAMPIONSLEAGUE"),
            r"\bchampions league\b|\bUCL\b",
            odds_sport="soccer_uefa_champs_league", three_way=True,
        ),
        League(
            "MLS", "MLS", "soccer", 2, "Feb–Dec",
            ("KXMLS",),
            r"\bMLS\b|\bmajor league soccer\b",
            odds_sport="soccer_usa_mls", three_way=True,
        ),
        League(
            "LALIGA", "La Liga", "soccer", 3, "Aug–May",
            ("KXLALIGA",),
            r"\bla liga\b",
            odds_sport="soccer_spain_la_liga", three_way=True,
        ),
        League(
            "SERIEA", "Serie A", "soccer", 3, "Aug–May",
            ("KXSERIEA",),
            r"\bserie a\b",
            odds_sport="soccer_italy_serie_a", three_way=True,
        ),
        League(
            "BUNDESLIGA", "Bundesliga", "soccer", 3, "Aug–May",
            ("KXBUNDESLIGA",),
            r"\bbundesliga\b",
            odds_sport="soccer_germany_bundesliga", three_way=True,
        ),
        League(
            "LIGUE1", "Ligue 1", "soccer", 3, "Aug–May",
            ("KXLIGUE1",),
            r"\bligue 1\b",
            odds_sport="soccer_france_ligue_one", three_way=True,
        ),
    ]
}


def league_for_series(series: dict) -> str | None:
    for league in LEAGUES.values():
        if league.matches(series):
            return league.code
    return None


def get_league(code: str) -> League:
    try:
        return LEAGUES[code.upper()]
    except KeyError:
        raise SystemExit(f"Unknown league {code!r}. Choose from: {', '.join(LEAGUES)}") from None
