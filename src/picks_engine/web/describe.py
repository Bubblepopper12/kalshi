"""Plain-language formatting: money, cents, dates in the app's time zone, bet sentences.

The game model itself (outcomes, prices, sportsbook comparison) lives in live/board.py.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from decimal import Decimal


try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

KIND_LABELS = {
    "moneyline": ("Who wins", "Pick the team you think wins the whole game."),
    "spread": ("Win by how much", "Bet on a team winning by more than a number of points."),
    "total": ("Total points", "Bet on whether both teams together score over a number."),
}

def local_zone():
    name = os.environ.get("APP_TIMEZONE", "America/Chicago")
    try:
        return ZoneInfo(name) if ZoneInfo else timezone.utc
    except Exception:  # unknown zone name or no tz database
        return timezone.utc


def when(value: str | datetime | None) -> str:
    """'Sun, Oct 18 · 3:25 PM' in the app's time zone (Central by default)."""
    if not value:
        return ""
    dt = value if isinstance(value, datetime) else None
    if dt is None:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(local_zone())
    return local.strftime("%a, %b %-d · %-I:%M %p")


def day_label(d: date | None) -> str:
    return d.strftime("%a, %b %-d") if d else ""


def money(value: Decimal | float | int) -> str:
    return f"${Decimal(str(value)):,.2f}"


def qty(value) -> str:
    """Contracts: whole numbers as "21", fractional ones as "0.43" (Kalshi allows fractions)."""
    if value is None:
        return "0"
    d = Decimal(str(value))
    if d == d.to_integral_value():
        return f"{int(d):,}"
    return f"{d.normalize():,f}".rstrip("0").rstrip(".")


def cents(value: Decimal | None) -> str:
    return "—" if value is None else f"{Decimal(value) * 100:.0f}¢"


def bet_sentence(statement: str, side: str) -> str:
    return statement if side == "yes" else f"NOT: {statement}"
