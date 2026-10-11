"""Team nicknames, so a search for "eagles" or "lakers" finds Kalshi's "Philadelphia" / "Los Angeles L".

Kalshi names NFL and NBA teams by city ("New York G", "Los Angeles C"). Keys are
lower-case Kalshi names; values are extra words to search on. Unknown names just
search on what Kalshi shows.
"""

NFL = {
    "arizona": "cardinals", "atlanta": "falcons", "baltimore": "ravens", "buffalo": "bills",
    "carolina": "panthers", "chicago": "bears", "cincinnati": "bengals", "cleveland": "browns",
    "dallas": "cowboys", "denver": "broncos", "detroit": "lions", "green bay": "packers",
    "houston": "texans", "indianapolis": "colts", "jacksonville": "jaguars jags", "kansas city": "chiefs",
    "las vegas": "raiders", "los angeles c": "chargers", "los angeles r": "rams", "miami": "dolphins",
    "minnesota": "vikings", "new england": "patriots pats", "new orleans": "saints", "new york g": "giants",
    "new york j": "jets", "philadelphia": "eagles", "pittsburgh": "steelers", "san francisco": "49ers niners",
    "seattle": "seahawks", "tampa bay": "buccaneers bucs", "tennessee": "titans", "washington": "commanders",
}

NBA = {
    "atlanta": "hawks", "boston": "celtics", "brooklyn": "nets", "charlotte": "hornets", "chicago": "bulls",
    "cleveland": "cavaliers cavs", "dallas": "mavericks mavs", "denver": "nuggets", "detroit": "pistons",
    "golden state": "warriors dubs", "houston": "rockets", "indiana": "pacers", "los angeles c": "clippers",
    "los angeles l": "lakers", "memphis": "grizzlies", "miami": "heat", "milwaukee": "bucks",
    "minnesota": "timberwolves wolves", "new orleans": "pelicans", "new york": "knicks",
    "oklahoma city": "thunder okc", "orlando": "magic", "philadelphia": "76ers sixers", "phoenix": "suns",
    "portland": "trail blazers blazers", "sacramento": "kings", "san antonio": "spurs", "toronto": "raptors",
    "utah": "jazz", "washington": "wizards",
}

BY_LEAGUE = {"NFL": NFL, "NBA": NBA}


def extra_words(league: str, name: str) -> str:
    return BY_LEAGUE.get(league, {}).get((name or "").strip().lower(), "")
