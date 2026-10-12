"""Game start times from ESPN's public scoreboard (no key needed), for all 10 leagues.

Kalshi doesn't publish when a game starts, and grading a bet needs the price just before
kickoff, so the start time comes from here: one request per league per day, cached.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime

import httpx

from .teams import name_matches

SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
PATHS = {"NFL": "football/nfl", "CFB": "football/college-football", "NBA": "basketball/nba",
         "EPL": "soccer/eng.1", "UCL": "soccer/uefa.champions", "MLS": "soccer/usa.1",
         "LALIGA": "soccer/esp.1", "SERIEA": "soccer/ita.1", "BUNDESLIGA": "soccer/ger.1",
         "LIGUE1": "soccer/fra.1"}
TTL = 6 * 3600


@dataclass
class EspnGame:
    start: datetime
    home: list[str]  # every name ESPN gives the team: "Philadelphia Eagles", "Eagles", "Philadelphia", "PHI"
    away: list[str]


_cache: dict[tuple[str, date], tuple[float, list[EspnGame]]] = {}


def _names(team: dict) -> list[str]:
    return [n for n in (team.get("displayName"), team.get("shortDisplayName"), team.get("location"),
                        team.get("name"), team.get("abbreviation")) if n]


def parse(data: dict) -> list[EspnGame]:
    out = []
    for ev in data.get("events") or []:
        comp = (ev.get("competitions") or [{}])[0]
        when = comp.get("date") or ev.get("date")
        try:
            start = datetime.fromisoformat(when.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            continue
        sides = {c.get("homeAway"): _names(c.get("team") or {}) for c in comp.get("competitors") or []}
        if sides.get("home") and sides.get("away"):
            out.append(EspnGame(start, sides["home"], sides["away"]))
    return out


def games_on(league: str, day: date, transport: httpx.BaseTransport | None = None) -> list[EspnGame]:
    if league not in PATHS:
        return []
    hit = _cache.get((league, day))
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    params = {"dates": day.strftime("%Y%m%d"), "limit": 500}
    if league == "CFB":
        params["groups"] = 80  # every FBS game, not just the featured ones
    try:
        with httpx.Client(timeout=15, transport=transport) as http:
            resp = http.get(SCOREBOARD.format(path=PATHS[league]), params=params)
            resp.raise_for_status()
            games = parse(resp.json())
    except (httpx.HTTPError, ValueError):
        return []  # not cached: try again next time
    _cache[(league, day)] = (time.time(), games)
    return games


def _team_is(kalshi_name: str, names: list[str]) -> bool:
    return any(name_matches(kalshi_name, n) or name_matches(n, kalshi_name) for n in names)


def find_start(league: str, day: date | None, teams: list[str],
               transport: httpx.BaseTransport | None = None) -> datetime | None:
    """Kickoff of the game between `teams` (Kalshi's names) on `day` or the day either side."""
    if day is None or len(teams) != 2:
        return None
    a, b = teams
    for d in (day, date.fromordinal(day.toordinal() - 1), date.fromordinal(day.toordinal() + 1)):
        found = [g for g in games_on(league, d, transport)
                 if (_team_is(a, g.home) and _team_is(b, g.away)) or (_team_is(a, g.away) and _team_is(b, g.home))]
        if len(found) == 1:
            return found[0].start
    return None


def clear() -> None:
    _cache.clear()
