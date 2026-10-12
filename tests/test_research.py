import json
from datetime import datetime, timezone

import httpx
import pytest

from picks_engine import reference, research
from picks_engine.kalshi.client import KalshiReadOnlyClient

EVENT = "KXEPLGAME-26OCT04ARSMUN"
# Arsenal v Man United, Sat Oct 4 2026 15:00 UK time (BST) = 14:00 UTC
KICKOFF = int(datetime(2026, 10, 4, 14, 0, tzinfo=timezone.utc).timestamp())
FOOTBALL_DATA = (
    "﻿Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,PSCH,PSCD,PSCA,AvgCH,AvgCD,AvgCA\n"
    "E0,04/10/2026,15:00,Arsenal,Man United,2,0,H,1.80,3.80,4.80,1.78,3.70,4.70\n"
    "E0,04/10/2026,17:30,Nott'm Forest,Wolves,1,1,D,,,,2.40,3.20,3.10\n"
    "E0,05/10/2026,14:00,Chelsea,Liverpool,,,,,,,,,\n"
)


def candles(asks, start_hour=10):
    base = int(datetime(2026, 10, 4, start_hour, tzinfo=timezone.utc).timestamp())
    return [{"end_period_ts": base + i * 3600, "yes_ask": {"close": a}, "yes_bid": {"close": a - 2},
             "price": {"close": a - 1}, "volume": 50} for i, a in enumerate(asks)]


# Prices at 10:00..15:00 UTC. The last one at least an hour before kickoff is 13:00.
MARKETS = {
    f"{EVENT}-ARS": ("Arsenal", "yes", candles([52, 52, 53, 50, 80, 99])),
    f"{EVENT}-MUN": ("Manchester United", "no", candles([23, 23, 22, 22, 8, 1])),
    f"{EVENT}-TIE": ("Tie", "no", candles([27, 27, 27, 28, 14, 1])),
}


def kalshi(request: httpx.Request) -> httpx.Response:
    path = request.url.path.split("/trade-api/v2")[1]
    if path == "/series":
        return httpx.Response(200, json={"series": [
            {"ticker": "KXEPLGAME", "title": "Premier League Game", "category": "Sports"}]})
    if path == "/markets":
        if request.url.params["series_ticker"] != "KXEPLGAME":
            return httpx.Response(200, json={"markets": [], "cursor": ""})
        return httpx.Response(200, json={"markets": [
            {"ticker": t, "event_ticker": EVENT, "yes_sub_title": team, "result": result,
             "open_time": "2026-09-28T12:00:00Z", "close_time": "2026-10-04T18:00:00Z",
             "expected_expiration_time": "2026-10-04T16:00:00Z"} for t, (team, result, _) in MARKETS.items()],
            "cursor": ""})
    if path.endswith("/candlesticks"):
        return httpx.Response(200, json={"candlesticks": MARKETS[path.split("/")[-2]][2]})
    return httpx.Response(404)


def client():
    return KalshiReadOnlyClient("https://kalshi.test/trade-api/v2", requests_per_second=0,
                                transport=httpx.MockTransport(kalshi), max_retries=0)


def test_soccer_sources_cover_each_season():
    urls = reference.soccer_sources("EPL", datetime(2025, 8, 1), until=datetime(2026, 10, 12))
    assert urls == ["https://www.football-data.co.uk/mmz4281/2526/E0.csv",
                    "https://www.football-data.co.uk/mmz4281/2627/E0.csv"]
    assert reference.soccer_sources("MLS", datetime(2025, 8, 1)) == ["https://www.football-data.co.uk/new/USA.csv"]
    assert reference.soccer_sources("NBA", datetime(2025, 8, 1)) == []


def test_parse_football_data():
    games = reference.parse_football_data(FOOTBALL_DATA)
    assert len(games) == 2  # the game without odds is skipped
    ars, forest = games
    assert ars.kickoff == KICKOFF and ars.away == "Manchester United"
    assert sum(ars.fair.values()) == pytest.approx(1)
    assert ars.fair["home"] > ars.fair["away"]
    assert forest.home == "Nott'm Forest" and forest.fair["draw"] == pytest.approx(0.30, abs=0.02)  # average odds


def test_research_end_to_end(tmp_path):
    fetched = []

    def fetch(url):
        fetched.append(url)
        if url.endswith("2627/E0.csv"):
            return FOOTBALL_DATA
        raise httpx.HTTPStatusError("missing", request=httpx.Request("GET", url),
                                    response=httpx.Response(404))

    out = research.run(client(), ["EPL", "NBA"], datetime(2026, 9, 1, tzinfo=timezone.utc),
                       reports=tmp_path / "reports", data=tmp_path / "data", fetch=fetch,
                       progress=lambda *_: None)
    epl, nba = out
    assert epl.markets == 3 and epl.games == 1 and "football-data" in epl.source
    assert epl.tag == "few"  # one game: far too few to judge
    assert any("3+ points cheaper" in p for p in epl.points)
    assert nba.tag == "error" and "no game-winner series" in nba.error

    text = (tmp_path / "reports" / "EPL.md").read_text()
    assert "3 Kalshi prices matched" in text
    assert "Does Kalshi lag earlier in the week?" in text  # kickoff known from the UK time
    summary = json.loads((tmp_path / "reports" / "summary.json").read_text())
    assert [x["code"] for x in summary["leagues"]] == ["EPL", "NBA"]
    assert "All leagues together" in (tmp_path / "reports" / "summary.md").read_text()


def test_judge_wording():
    from picks_engine import history

    rep = history.Report(markets=900, buckets=[history.Bucket(lo, lo + 10) for lo in range(0, 100, 10)], games=300)
    rep.buckets[0].n, rep.buckets[0].pnl = 150, -30.0
    rep.comparison = history.Comparison(900, 0.60, 0.61, [history.Rule("any", 400, 200, -10),
                                                          history.Rule("3+", 250, 120, 12.5),
                                                          history.Rule("5+", 90, 40, 2)])
    s = research.judge("EPL", rep)
    assert s.tag == "edge" and "about as accurate" in s.points[0]
    assert any("Avoid them" in p for p in s.points)
    rep.comparison.rules[1] = history.Rule("3+", 250, 100, -20)
    assert research.judge("EPL", rep).tag == "none"
    rep.comparison = None
    assert research.judge("EPL", rep).tag == "kalshi-only"
