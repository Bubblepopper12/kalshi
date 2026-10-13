"""League definitions and how to find each league's series in Kalshi's live listings.

Kalshi's soccer depth varies by league and new series appear without notice, so
league membership comes from the live /series listing (ticker prefix or title).
Game-by-game series follow Kalshi's naming (KXNFLGAME, KXEPLGAME, ...); see
game_series() for how they're picked out of everything else a league lists.
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
    exact_tickers: tuple[str, ...] = ()  # one-off series matched only by their full ticker (e.g. KXSB)

    @property
    def game_prefix(self) -> str:
        """The league's main ticker prefix, e.g. KXNFL (game series are KXNFLGAME, KXNFLSPREAD, ...)."""
        return self.ticker_prefixes[0]

    def matches(self, series: dict) -> bool:
        ticker = (series.get("ticker") or "").upper()
        title = series.get("title") or ""
        if self.exclude_pattern and re.search(self.exclude_pattern, f"{ticker} {title}", re.I):
            return False
        if ticker in self.exact_tickers or ticker.startswith(self.ticker_prefixes):
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
            ("KXNFL", "KXMVENFL"),
            r"\bNFL\b|\bpro football\b|\bsuper bowl\b",
            exact_tickers=("KXSB",),  # not a prefix: KXSBL... is Slovak basketball
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


GAME_SUFFIX = {"moneyline": "GAME", "spread": "SPREAD", "total": "TOTAL", "btts": "BTTS"}
_PARTIAL_TITLE = re.compile(r"\b(1st|2nd|3rd|4th|first|second|third|fourth)\s+(half|quarter|period)\b"
                            r"|\bhalftime\b|\bquarter\b", re.I)


def game_series(league: League, series: list[dict], kind: str = "moneyline") -> list[dict]:
    """The league's game-by-game series of one kind, out of everything Kalshi lists.

    Exact name first (KXNFLGAME); if Kalshi ever renames it, fall back to series
    under the league's own prefixes whose ticker ends in GAME/SPREAD/TOTAL.
    Combos (KXMVE...), futures, specials and half/quarter markets never qualify.
    """
    suffix = GAME_SUFFIX[kind]
    by_ticker = {(s.get("ticker") or "").upper(): s for s in series}
    exact = by_ticker.get(league.game_prefix + suffix)
    if exact:
        return [exact]
    own = tuple(p for p in league.ticker_prefixes if not p.startswith("KXMVE"))
    found = []
    for ticker, s in by_ticker.items():
        if not (ticker.startswith(own) and ticker.endswith(suffix)):
            continue
        core = ticker[len(next(p for p in own if ticker.startswith(p))):]
        title = s.get("title") or ""
        if re.search(r"[1-4][HQ]|HALF|QUARTER|QTR|PERIOD", core) or _PARTIAL_TITLE.search(title):
            continue
        if league.exclude_pattern and re.search(league.exclude_pattern, f"{ticker} {title}", re.I):
            continue
        found.append(s)
    return sorted(found, key=lambda s: len(s.get("ticker") or ""))[:2]
