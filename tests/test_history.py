import csv
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest

from picks_engine import history
from picks_engine.kalshi.client import KalshiReadOnlyClient

EVENT = "KXNFLGAME-26OCT05DALPHI"
ARCHIVED = "KXNFLGAME-26SEP07WASNYG"  # settled before Kalshi's historical cutoff
# Kickoff Sun Oct 5 2026, 4:25 PM Eastern (daylight time) = 20:25 UTC
KICKOFF = int(datetime(2026, 10, 5, 20, 25, tzinfo=timezone.utc).timestamp())
NFLVERSE = ("game_id,season,game_type,week,gameday,gametime,away_team,home_team,away_moneyline,home_moneyline\n"
            "2026_05_DAL_PHI,2026,REG,5,2026-10-05,16:25,DAL,PHI,170,-200\n")


def candles(asks):
    """Hourly candles ending 18:00, 19:00, 20:00, 21:00 UTC on game day."""
    base = int(datetime(2026, 10, 5, 18, tzinfo=timezone.utc).timestamp())
    return [{"end_period_ts": base + i * 3600, "yes_ask": {"close": a}, "yes_bid": {"close": a - 2},
             "price": {"close": a - 1}, "volume": 100} for i, a in enumerate(asks)]


MARKETS = {
    f"{EVENT}-PHI": ("Philadelphia", "yes", candles([58, 59, 70, 99])),
    f"{EVENT}-DAL": ("Dallas", "no", candles([43, 42, 31, 1])),
    "KXNFLGAME-26AUG01OLDOLD-OLD": ("Old", "yes", candles([50])),  # before --since: skipped
}


def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path.split("/trade-api/v2")[1]
    if path == "/series":
        return httpx.Response(200, json={"series": [{"ticker": "KXNFLGAME", "title": "Pro Football Game",
                                                     "category": "Sports"}]})
    if path == "/markets":
        assert request.url.params["status"] == "settled"
        out = []
        for t, (team, result, _) in MARKETS.items():
            old = "OLD" in t
            out.append({"ticker": t, "event_ticker": t.rsplit("-", 1)[0], "yes_sub_title": team, "result": result,
                        "open_time": "2026-09-28T12:00:00Z",
                        "close_time": "2026-08-02T04:00:00Z" if old else "2026-10-06T04:00:00Z",
                        "expected_expiration_time": "2026-10-06T00:30:00Z"})
        return httpx.Response(200, json={"markets": out, "cursor": ""})
    if path == "/historical/markets":
        return httpx.Response(200, json={"markets": [
            {"ticker": f"{ARCHIVED}-NYG", "event_ticker": ARCHIVED, "yes_sub_title": "New York G", "result": "yes",
             "open_time": "2026-09-01T12:00:00Z", "close_time": "2026-09-08T04:00:00Z",
             "expected_expiration_time": "2026-09-08T00:30:00Z"}], "cursor": ""})
    if path.startswith("/historical/markets/"):
        return httpx.Response(200, json={"candlesticks": candles([40, 41])})
    if path.endswith("/candlesticks"):
        ticker = path.split("/")[-2]
        assert request.url.params["period_interval"] == "60"
        return httpx.Response(200, json={"candlesticks": MARKETS[ticker][2]})
    return httpx.Response(404)


@pytest.fixture
def downloaded(tmp_path):
    client = KalshiReadOnlyClient("https://kalshi.test/trade-api/v2", requests_per_second=0,
                                  transport=httpx.MockTransport(handler))
    out = tmp_path / "hist.csv"
    rows = history.download(client, "NFL", datetime(2026, 9, 1, tzinfo=timezone.utc), out, progress=lambda *_: None)
    return out, rows


def test_download_writes_hourly_rows(downloaded):
    out, rows = downloaded
    data = list(csv.DictReader(out.open()))
    assert rows == 10 and len(data) == 10  # 2 markets x 4 candles + 2 archived; the August market is skipped
    assert sum(r["ticker"] == f"{ARCHIVED}-NYG" for r in data) == 2
    phi = [r for r in data if r["ticker"].endswith("PHI")]
    assert phi[0]["team"] == "Philadelphia" and phi[0]["result"] == "yes"
    assert Decimal(phi[1]["yes_ask"]) == Decimal("0.59") and Decimal(phi[1]["yes_bid"]) == Decimal("0.57")


def test_candle_price_formats():
    assert history._close({"yes_ask": {"close": 55}}, "yes_ask") == Decimal("0.55")
    assert history._close({"yes_ask": {"close_dollars": "0.5550"}}, "yes_ask") == Decimal("0.5550")
    assert history._close({"yes_ask_close": 40}, "yes_ask") == Decimal("0.40")
    assert history._close({}, "yes_ask") is None
    assert history._close({"yes_ask": {"close": "0.5500"}}, "yes_ask") == Decimal("0.55")  # dollars, archive style
    assert history._close({"yes_ask": {"close": 0.07}}, "yes_ask") == Decimal("0.07")
    assert history._close({"yes_ask": {"close": "7"}}, "yes_ask") == Decimal("0.07")


def test_pregame_snapshot_uses_nfl_kickoff(downloaded):
    out, _ = downloaded
    snaps = history.load_snapshots(out)
    kickoffs, fair = history.nfl_match(snaps, history.nflverse_games(NFLVERSE))
    assert kickoffs[EVENT] == KICKOFF  # Eastern daylight time handled
    pre = {s.ticker: s for s in history.load_snapshots(out, kickoffs)}
    assert pre[f"{EVENT}-PHI"].ask == Decimal("0.59")  # last candle at least 1 hour before kickoff
    assert fair[f"{EVENT}-PHI"][0] == pytest.approx(0.651, abs=0.005)
    assert fair[f"{EVENT}-DAL"][0] == pytest.approx(0.349, abs=0.005)


def test_report(downloaded):
    out, _ = downloaded
    report = history.analyze(out, "NFL", NFLVERSE)
    assert report.markets == 2
    by_low = {b.low: b for b in report.buckets}
    assert by_low[50].n == 1 and by_low[50].wins == 1 and by_low[40].n == 1 and by_low[40].wins == 0
    text = report.markdown("NFL")
    assert "longshot bias" in text and "2 Kalshi prices matched" in text
    # Philadelphia: books 65.1% vs Kalshi 59c + 1.7c fee = ~4.4 points cheaper -> bought and won
    assert "| Kalshi any points cheaper than the books | 1 | 1 |" in text
    assert "| Kalshi 3+ points cheaper than the books | 1 | 1 |" in text
    assert "| Kalshi 5+ points cheaper than the books | 0 | 0 |" in text


def test_report_without_sportsbook_data(downloaded):
    out, _ = downloaded
    report = history.analyze(out, "NFL", None)
    assert report.markets == 2 and report.strategy == []


def test_timing_table(downloaded):
    out, _ = downloaded
    text = history.analyze(out, "NFL", NFLVERSE).markdown("NFL")
    assert "Does Kalshi lag earlier in the week?" in text
    assert "| 1 h | 2 |" in text  # both markets have a price an hour before kickoff
    assert "| 72 h | 0 |" in text  # the fake history only starts on game day


def test_update_only_downloads_new_markets(tmp_path):
    calls = []

    def counting(request):
        if request.url.path.endswith("/candlesticks"):
            calls.append(request.url.path)
        return handler(request)

    client = KalshiReadOnlyClient("https://kalshi.test/trade-api/v2", requests_per_second=0,
                                  transport=httpx.MockTransport(counting))
    out = tmp_path / "hist.csv"
    since = datetime(2026, 9, 1, tzinfo=timezone.utc)
    first = history.download(client, "NFL", since, out, progress=lambda *_: None, update=True)
    n = len(calls)
    again = history.download(client, "NFL", since, out, progress=lambda *_: None, update=True)
    assert first == 10 and again == 0 and len(calls) == n  # nothing new: no candle requests
    assert len(list(csv.DictReader(out.open()))) == 10  # earlier rows kept
