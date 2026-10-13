"""Sportsbook prices from The Odds API (https://the-odds-api.com), read-only.

One call per league returns every upcoming game with each bookmaker's
moneyline. Up to 10 bookmakers count as one request against the plan quota;
the remaining quota comes back in the x-requests-remaining header.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

BASE_URL = "https://api.the-odds-api.com/v4"
# Sharp book first, then the big US books. Ten or fewer keeps each call at one request.
DEFAULT_BOOKMAKERS = "pinnacle,draftkings,fanduel,betmgm,williamhill_us,betrivers,bovada,betonlineag,lowvig"


class OddsAPIError(RuntimeError):
    pass


@dataclass
class OddsResult:
    events: list[dict]
    requests_remaining: int | None


class OddsAPIClient:
    def __init__(self, api_key: str, bookmakers: str = DEFAULT_BOOKMAKERS,
                 transport: httpx.BaseTransport | None = None, base_url: str = BASE_URL):
        if not api_key:
            raise OddsAPIError("ODDS_API_KEY is not set")
        self._key = api_key
        self._bookmakers = bookmakers
        self._http = httpx.Client(base_url=base_url, timeout=httpx.Timeout(20.0), transport=transport)

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def moneylines(self, sport_key: str, markets: str = "h2h") -> OddsResult:
        """Each game's odds. markets="h2h,spreads,totals" adds main spreads/totals (each market costs a request)."""
        params = {"apiKey": self._key, "markets": markets, "oddsFormat": "american", "dateFormat": "iso"}
        resp = self._http.get(f"/sports/{sport_key}/odds", params=params | {"bookmakers": self._bookmakers})
        if resp.status_code == 422:  # a bookmaker name it doesn't know: fall back to every US book
            resp = self._http.get(f"/sports/{sport_key}/odds", params=params | {"regions": "us"})
        if resp.status_code == 401:
            raise OddsAPIError("The Odds API rejected ODDS_API_KEY (check it in Vercel).")
        if resp.status_code == 429:
            raise OddsAPIError("The Odds API quota is used up for now.")
        if resp.status_code >= 400:
            raise OddsAPIError(f"The Odds API returned HTTP {resp.status_code}: {resp.text[:200]}")
        remaining = resp.headers.get("x-requests-remaining")
        try:
            left = int(float(remaining)) if remaining is not None else None
        except ValueError:
            left = None
        data = resp.json()
        return OddsResult(events=data if isinstance(data, list) else [], requests_remaining=left)
