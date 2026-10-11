from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest

from picks_engine.live.odds_api import OddsAPIClient, OddsAPIError
from picks_engine.live.picks import book_views, build_picks, size
from picks_engine.live.teams import assign, name_matches

NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)


def kalshi_event(code, title, teams, asks, tie_ask=None):
    ev = f"KXNFLGAME-{code}"
    # Kalshi's yes_ask is in cents; the helper takes dollars for readability.
    markets = [{"ticker": f"{ev}-{i}", "yes_sub_title": t, "yes_ask": round(a * 100), "status": "active"}
               for i, (t, a) in enumerate(zip(teams, asks))]
    if tie_ask is not None:
        markets.append({"ticker": f"{ev}-TIE", "yes_sub_title": "Tie", "yes_ask": round(tie_ask * 100),
                        "status": "active"})
    return {"event_ticker": ev, "title": title, "markets": markets}


def odds_event(home, away, books, commence="2026-10-18T17:00:00Z", draw=None):
    out = []
    for i, (h, a) in enumerate(books):
        outcomes = [{"name": home, "price": h}, {"name": away, "price": a}]
        if draw is not None:
            outcomes.append({"name": "Draw", "price": draw[i]})
        out.append({"key": f"b{i}", "title": f"Book{i}", "markets": [
            {"key": "h2h", "last_update": "2026-10-17T11:55:00Z", "outcomes": outcomes}]})
    return {"home_team": home, "away_team": away, "commence_time": commence, "bookmakers": out}


@pytest.mark.parametrize("kalshi,book,ok", [
    ("Philadelphia", "Philadelphia Eagles", True), ("New York G", "New York Giants", True),
    ("New York G", "New York Jets", False), ("Los Angeles C", "Los Angeles Rams", False),
    ("Man City", "Manchester City", True), ("Man City", "Manchester United", False),
    ("Wolves", "Wolverhampton Wanderers", True), ("Ohio St.", "Ohio State Buckeyes", True),
])
def test_name_matching(kalshi, book, ok):
    assert name_matches(kalshi, book) is ok


def test_ambiguous_games_are_not_guessed():
    assert assign(["Jacksonville", "Philadelphia"], "Philadelphia Eagles", "Jacksonville Jaguars") == \
        {"Jacksonville": "away", "Philadelphia": "home"}
    assert assign(["Miami", "Miami (OH)"], "Miami Hurricanes", "Miami (OH) RedHawks") is None


def test_consensus_removes_the_margin():
    oe = odds_event("Philadelphia Eagles", "Jacksonville Jaguars", [(-200, 170), (-190, 160), (-210, 175)])
    v = book_views(oe, three_way=False)
    assert 0.64 < v["home"].fair < 0.67 and v["home"].fair + v["away"].fair == pytest.approx(1, abs=0.01)
    assert len(v["home"].books) == 3


def test_pick_when_kalshi_is_cheaper():
    ev = kalshi_event("26OCT18JACPHI", "Jacksonville at Philadelphia", ["Jacksonville", "Philadelphia"],
                      [0.37, 0.58])
    oe = odds_event("Philadelphia Eagles", "Jacksonville Jaguars", [(-200, 170), (-190, 160), (-210, 175)])
    r = build_picks([ev], [oe], three_way=False, now=NOW)
    assert r.games_checked == 1 and r.games_matched == 1
    assert [p.outcome for p in r.picks] == ["Philadelphia wins"]
    p = r.picks[0]
    # fair ~65.6%, cost 58c + 1.7c fee -> edge ~6 points
    assert p.edge == pytest.approx(p.fair - float(p.ask + p.fee)) and 0.05 < p.edge < 0.07
    size(p, Decimal("50"), max_order=5)
    assert p.contracts == 2  # quarter-Kelly: 0.25 x (0.651 - 0.597) / 0.403 x $50 = $1.68
    size(p, Decimal("500"), max_order=5)
    assert p.contracts == 8 and p.stake <= Decimal("5")  # Kelly says $16.80; the $5 per-bet cap wins
    size(p, None, max_order=5)
    assert p.contracts == 8  # no balance known: only the cap applies


def test_no_pick_when_fair_and_started_games_skipped():
    ev = kalshi_event("26OCT18JACPHI", "Jacksonville at Philadelphia", ["Jacksonville", "Philadelphia"],
                      [0.36, 0.67])
    oe = odds_event("Philadelphia Eagles", "Jacksonville Jaguars", [(-200, 170), (-190, 160)])
    r = build_picks([ev], [oe], three_way=False, now=NOW)
    assert r.picks == [] and all(p.edge < 0.03 for p in r.near)
    started = build_picks([ev], [oe], three_way=False, now=datetime(2026, 10, 18, 18, tzinfo=timezone.utc))
    assert started.games_matched == 0 and started.picks == []


def test_soccer_draw_and_single_book_ignored():
    ev = kalshi_event("26OCT18ARSCHE", "Arsenal vs Chelsea", ["Arsenal", "Chelsea"], [0.45, 0.25], tie_ask=0.20)
    oe = odds_event("Arsenal", "Chelsea", [(110, 300, ), (105, 290)], draw=[250, 255])
    r = build_picks([ev], [oe], three_way=True, now=NOW)
    outcomes = {p.outcome for p in r.picks + r.near}
    assert "It ends in a tie" in outcomes  # draw priced from the books' Draw line
    one_book = odds_event("Arsenal", "Chelsea", [(110, 300)], draw=[250])
    assert build_picks([ev], [one_book], three_way=True, now=NOW).picks == []


def test_unmatched_games_are_reported():
    ev = kalshi_event("26OCT18JACPHI", "Jacksonville at Philadelphia", ["Jacksonville", "Philadelphia"], [0.4, 0.6])
    r = build_picks([ev], [odds_event("Dallas Cowboys", "New York Giants", [(-150, 130)] * 2)],
                    three_way=False, now=NOW)
    assert r.unmatched == ["Jacksonville at Philadelphia"] and r.games_matched == 0


def test_odds_client_quota_and_errors():
    calls = []

    def handler(request):
        calls.append(request)
        if "bookmakers" in request.url.params:
            return httpx.Response(422, json={"message": "unknown bookmaker"})
        return httpx.Response(200, json=[{"home_team": "A"}], headers={"x-requests-remaining": "487"})

    with OddsAPIClient("k", transport=httpx.MockTransport(handler)) as c:
        res = c.moneylines("americanfootball_nfl")
    assert res.requests_remaining == 487 and res.events == [{"home_team": "A"}]
    assert calls[1].url.params["regions"] == "us"  # fell back after the bookmaker list was refused
    bad = OddsAPIClient("k", transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    with pytest.raises(OddsAPIError, match="rejected"):
        bad.moneylines("americanfootball_nfl")
    with pytest.raises(OddsAPIError):
        OddsAPIClient("")


def test_strong_needs_pinnacle():
    ev = kalshi_event("26OCT18JACPHI", "Jacksonville at Philadelphia", ["Jacksonville", "Philadelphia"],
                      [0.37, 0.55])
    books = [(-200, 170), (-190, 160), (-210, 175)]
    oe = odds_event("Philadelphia Eagles", "Jacksonville Jaguars", books)
    no_sharp = build_picks([ev], [oe], three_way=False, now=NOW).picks[0]
    assert no_sharp.strength == "Good" and any("didn't price" in n for n in no_sharp.notes)
    oe["bookmakers"][0]["key"] = "pinnacle"
    sharp = build_picks([ev], [oe], three_way=False, now=NOW).picks[0]
    assert sharp.strength == "Strong" and sharp.choice.pinnacle is not None


def test_started_games_stay_on_the_board():
    ev = kalshi_event("26OCT18JACPHI", "Jacksonville at Philadelphia", ["Jacksonville", "Philadelphia"], [0.37, 0.55])
    oe = odds_event("Philadelphia Eagles", "Jacksonville Jaguars", [(-200, 170), (-190, 160)])
    r = build_picks([ev], [oe], three_way=False, now=datetime(2026, 10, 18, 18, tzinfo=timezone.utc))
    assert r.in_progress == 1 and len(r.board) == 1 and r.picks == [] and r.board[0].starts is not None
