"""Match Kalshi's short team names to sportsbook names.

Kalshi uses names like "Philadelphia", "New York G" or "Man City"; sportsbooks
use "Philadelphia Eagles", "New York Giants", "Manchester City". A Kalshi name
matches when every one of its words matches a word of the sportsbook name:
equal, a single letter that starts the word ("G" -> "Giants"), or a 3+ letter
prefix ("Man" -> "Manchester"). A game only counts as matched when each Kalshi
team maps to a different side of exactly one sportsbook game.
"""

from __future__ import annotations

import re
import unicodedata

ALIASES = {
    "la": "los angeles", "ny": "new york", "st": "state", "st.": "state", "utd": "united",
    "spurs": "tottenham", "wolves": "wolverhampton", "psg": "paris saint germain",
    "inter": "internazionale inter", "atleti": "atletico", "bayern": "bayern munich",
    "gladbach": "monchengladbach", "nottm": "nottingham", "sheff": "sheffield",
}
DROP = {"fc", "cf", "sc", "afc", "the", "de", "club", "ac", "ssc", "as", "cd", "ud", "rc"}
DRAW_WORDS = {"tie", "draw"}


# Letters Unicode doesn't split into base letter + accent, so NFKD alone would drop them.
_SPECIAL = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "ß": "ss", "ł": "l", "Ł": "L",
                          "đ": "d", "Đ": "D", "ı": "i", "œ": "oe", "Œ": "OE"})


def words(name: str) -> list[str]:
    text = unicodedata.normalize("NFKD", (name or "").translate(_SPECIAL)).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\(([^)]*)\)", r" \1 ", text)
    out: list[str] = []
    for w in re.findall(r"[a-z0-9]+\.?", text):
        w = ALIASES.get(w, w).rstrip(".")
        for part in ALIASES.get(w, w).split():
            if part and part not in DROP:
                out.append(part)
    return out


def _fold(w: str) -> str:
    """Kalshi spells ø/ö/ü/ä as oe/ue/ae ("Bodoe"); sportsbooks often drop them to o/u/a."""
    return w.replace("oe", "o").replace("ue", "u").replace("ae", "a")


def _word_matches(k: str, book_words: list[str]) -> bool:
    return _plain_match(k, book_words) or _plain_match(_fold(k), [_fold(b) for b in book_words])


def _plain_match(k: str, book_words: list[str]) -> bool:
    for b in book_words:
        if k == b:
            return True
        if len(k) == 1 and b.startswith(k):
            return True
        if len(k) >= 3 and b.startswith(k):
            return True
    return False


def name_matches(kalshi_name: str, book_name: str) -> bool:
    kw, bw = words(kalshi_name), words(book_name)
    return bool(kw) and all(_word_matches(k, bw) for k in kw)


def is_draw(name: str) -> bool:
    return (name or "").strip().lower() in DRAW_WORDS


def assign(kalshi_names: list[str], home: str, away: str) -> dict[str, str] | None:
    """Map each Kalshi team name to 'home' or 'away' (draws skipped), or None if it doesn't fit."""
    teams = [n for n in kalshi_names if not is_draw(n)]
    if not teams:
        return None
    result: dict[str, str] = {}
    for n in teams:
        sides = [side for side, book in (("home", home), ("away", away)) if name_matches(n, book)]
        if len(sides) != 1:
            return None
        result[n] = sides[0]
    if len(set(result.values())) != len(result):
        return None
    return result
