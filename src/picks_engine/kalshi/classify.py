"""Map Kalshi series/markets onto the engine's pick types, and parse event tickers."""

from __future__ import annotations

import re
from datetime import date

MARKET_TYPES = ("moneyline", "spread", "total", "prop", "combo", "future", "other")

_TICKER_RULES: list[tuple[str, str]] = [
    ("combo", r"KXMVE|PARLAY|COMBO|MULTIGAME|SGP"),
    ("spread", r"SPREAD"),
    ("total", r"TOTAL"),
    # Futures before props: conference tickers like KXNBAEAST would otherwise hit "AST".
    ("future", r"KXSB\b|SUPERBOWL|CHAMP|MVP|ROTY|DPOY|OPOY|HEISMAN|PLAYOFF|DIVISION|CONF|EAST\b|WEST\b"
               r"|WINS\b|TITLE|TOP4|RELEGAT|AWARD|DRAFT|CUP\b"),
    ("prop", r"PASSYDS|RUSHYDS|RECYDS|RECS?\b|ANYTD|FIRSTTD|PASSTD|PTS|REB|AST|3PT|THREES|BLK|STL"
             r"|SOG|SHOTS|GOALSCORER|PLAYER|PRA\b"),
    ("moneyline", r"GAME|MATCH|WINNER"),
]

_TITLE_RULES: list[tuple[str, str]] = [
    ("combo", r"\bparlay\b|\bcombo\b|\bmulti-?game\b|\bsame game\b"),
    ("future", r"\bchampion|\bsuper bowl\b|\bmvp\b|\baward\b|\bplayoffs?\b|\bdivision\b|\bconference\b"
               r"|\bseason\b|\btitle\b|\brelegat|\btop (4|four)\b|\bdraft\b|\bheisman\b|\bcup winner\b"),
    ("prop", r"\byards\b|\btouchdowns?\b|\brebounds\b|\bassists\b|\bthrees\b|\bthree-pointers\b"
             r"|\bshots on goal\b|\bgoalscorer\b|\bscore a goal\b|\breceptions\b|\bplayer\b"),
    ("spread", r"\bspread\b|\bwin by (more|over)\b|\bby more than\b"),
    ("total", r"\btotal (points|goals)\b|\bover/under\b|\bcombined\b"),
    ("moneyline", r"\bwinner\b|\bto win\b|\bwin\b|\bvs\.?\b|\bat\b"),
]


def classify(series_ticker: str, title: str = "") -> str:
    ticker = (series_ticker or "").upper()
    for market_type, pattern in _TICKER_RULES:
        if re.search(pattern, ticker):
            return market_type
    for market_type, pattern in _TITLE_RULES:
        if re.search(pattern, title or "", re.I):
            return market_type
    return "other"


_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1
)}
_EVENT_RE = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})(\d{4})?([A-Z][A-Z0-9]*)?$")


def parse_event_ticker(event_ticker: str) -> tuple[date | None, str | None]:
    """KXNFLGAME-25SEP07DALPHI -> (2025-09-07, "DALPHI"). Returns (None, None) when it doesn't fit."""
    m = _EVENT_RE.search((event_ticker or "").upper())
    if not m or m.group(2) not in _MONTHS:
        return None, None
    yy, mon, dd, _hhmm, teams = m.groups()
    try:
        game_date = date(2000 + int(yy), _MONTHS[mon], int(dd))
    except ValueError:
        return None, None
    return game_date, teams


def split_teams_code(code: str, known_codes: set[str]) -> tuple[str, str] | None:
    """Split "DALPHI" into ("DAL", "PHI") using the set of team codes Kalshi uses for the league.

    Kalshi codes are 2-4 letters, so a concatenation can be ambiguous ("LACLAL").
    Only a split where both halves are known codes is accepted.
    """
    splits = [
        (code[:i], code[i:])
        for i in range(2, len(code) - 1)
        if code[:i] in known_codes and code[i:] in known_codes
    ]
    return splits[0] if len(splits) == 1 else None
