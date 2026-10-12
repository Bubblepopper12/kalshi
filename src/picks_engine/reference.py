"""Closing sportsbook lines for finished games, used to grade Kalshi's price history.

NFL:     nflverse games.csv (closing moneylines), handled in history.nfl_match.
Soccer:  football-data.co.uk season files: Pinnacle's closing odds (PSCH/PSCD/PSCA), or the
         market-average closing odds (AvgCH/AvgCD/AvgCA) when Pinnacle is missing.
         Premier League, La Liga, Serie A, Bundesliga, Ligue 1 and MLS.
College football, NBA and the Champions League have no free closing-line source, so their
reports run the Kalshi-only tests.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from .kalshi.classify import parse_event_ticker
from .live.teams import is_draw, name_matches
from .pricing.devig import devig

try:
    from zoneinfo import ZoneInfo
    _UK = ZoneInfo("Europe/London")
except Exception:  # pragma: no cover - no tz database
    _UK = timezone.utc

FOOTBALL_DATA = "https://www.football-data.co.uk/mmz4281/{season}/{division}.csv"
FOOTBALL_DATA_EXTRA = "https://www.football-data.co.uk/new/{country}.csv"
SOCCER_DIVISIONS = {"EPL": "E0", "LALIGA": "SP1", "SERIEA": "I1", "BUNDESLIGA": "D1", "LIGUE1": "F1"}
SOCCER_EXTRA = {"MLS": "USA"}  # one file with every season; its times aren't UK time, so no kickoffs

# football-data's short names that the word matcher can't work out by itself.
FD_NAMES = {
    "ath madrid": "Atletico Madrid", "ath bilbao": "Athletic Club Bilbao", "m'gladbach": "Monchengladbach",
    "sociedad": "Real Sociedad", "vallecano": "Rayo Vallecano", "espanol": "Espanyol", "betis": "Real Betis",
    "celta": "Celta Vigo", "paris sg": "Paris Saint Germain", "st etienne": "Saint Etienne",
    "ein frankfurt": "Eintracht Frankfurt", "fc koln": "Koln", "man united": "Manchester United",
    "man city": "Manchester City", "sp lisbon": "Sporting Lisbon", "la galaxy": "Los Angeles Galaxy",
}


@dataclass
class RefGame:
    """One finished game with the sportsbooks' closing no-vig chances."""

    id: str
    day: date
    home: str
    away: str
    fair: dict[str, float]  # "home" / "away" / "draw" -> chance
    kickoff: int | None = None  # UTC timestamp, when the source's clock is known


def soccer_sources(league: str, since: datetime, until: datetime | None = None) -> list[str]:
    """football-data URLs covering every season from `since` to now."""
    if league in SOCCER_EXTRA:
        return [FOOTBALL_DATA_EXTRA.format(country=SOCCER_EXTRA[league])]
    if league not in SOCCER_DIVISIONS:
        return []
    until = until or datetime.now(timezone.utc)
    first = since.year if since.month >= 7 else since.year - 1
    last = until.year if until.month >= 7 else until.year - 1
    return [FOOTBALL_DATA.format(season=f"{y % 100:02d}{(y + 1) % 100:02d}", division=SOCCER_DIVISIONS[league])
            for y in range(first, last + 1)]


def _decimal_to_american(d: float) -> float:
    return (d - 1) * 100 if d >= 2 else -100 / (d - 1)


def _odds(row: dict, *prefixes: str) -> tuple[float, float, float] | None:
    for p in prefixes:
        try:
            h, d, a = (float(row.get(f"{p}{x}") or "") for x in "HDA")
        except ValueError:
            continue
        if min(h, d, a) > 1:
            return h, d, a
    return None


def _day(text: str) -> date | None:
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def parse_football_data(text: str, uk_times: bool = True) -> list[RefGame]:
    """Games with closing 1X2 odds from a football-data CSV (main or 'new' format)."""
    out = []
    for i, row in enumerate(csv.DictReader(io.StringIO(text.lstrip("﻿")))):
        home, away = row.get("HomeTeam") or row.get("Home"), row.get("AwayTeam") or row.get("Away")
        day = _day(row.get("Date") or "")
        odds = _odds(row, "PSC", "AvgC", "MaxC", "B365C")
        if not (home and away and day and odds):
            continue
        h, d, a = devig([_decimal_to_american(o) for o in odds])
        kickoff = None
        if uk_times and (row.get("Time") or "").strip():
            try:
                hh, mm = (int(x) for x in row["Time"].strip().split(":")[:2])
                kickoff = int(datetime(day.year, day.month, day.day, hh, mm, tzinfo=_UK).timestamp())
            except ValueError:
                pass
        out.append(RefGame(f"{row.get('Div') or row.get('League') or 'fd'}-{day}-{i}", day,
                           FD_NAMES.get(home.strip().lower(), home.strip()),
                           FD_NAMES.get(away.strip().lower(), away.strip()),
                           {"home": h, "draw": d, "away": a}, kickoff))
    return out


def _same(a: str, b: str) -> bool:
    """Team names agree in either direction ("Dortmund" ~ "Borussia Dortmund")."""
    return name_matches(a, b) or name_matches(b, a)


def _sides(names: list[str], game: RefGame) -> dict[str, str] | None:
    """Map each Kalshi team name to the game's home/away side, or None if it doesn't fit cleanly."""
    result = {}
    for n in names:
        sides = [s for s, book in (("home", game.home), ("away", game.away)) if _same(n, book)]
        if len(sides) != 1:
            return None
        result[n] = sides[0]
    return result if len(set(result.values())) == len(result) == 2 else None


def name_match(snaps, games: list[RefGame]) -> tuple[dict[str, int], dict[str, tuple[float, str]]]:
    """(kickoff per Kalshi event, (closing fair chance, game id) per Kalshi market), matched by date and names."""
    by_day: dict[date, list[RefGame]] = defaultdict(list)
    for g in games:
        by_day[g.day].append(g)
    by_event = defaultdict(list)
    for s in snaps:
        by_event[s.event_ticker].append(s)
    kickoffs: dict[str, int] = {}
    fair: dict[str, tuple[float, str]] = {}
    for event, markets in by_event.items():
        day, _ = parse_event_ticker(event)
        teams = sorted({s.team for s in markets if not is_draw(s.team)})
        if not day or len(teams) != 2:
            continue
        found = [(g, sides) for d in (day, day - timedelta(days=1), day + timedelta(days=1))
                 for g in by_day.get(d, []) if (sides := _sides(teams, g))]
        if len(found) != 1:  # none, or ambiguous: skip rather than guess
            continue
        g, sides = found[0]
        if g.kickoff:
            kickoffs[event] = g.kickoff
        for s in markets:
            side = "draw" if is_draw(s.team) else sides.get(s.team)
            if side in g.fair:
                fair[s.ticker] = (g.fair[side], g.id)
    return kickoffs, fair
