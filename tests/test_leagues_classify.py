from datetime import date

from picks_engine.kalshi.classify import classify, parse_event_ticker, split_teams_code
from picks_engine.kalshi.leagues import LEAGUES, league_for_series


def test_league_matching():
    assert league_for_series({"ticker": "KXNFLGAME", "title": "x"}) == "NFL"
    assert league_for_series({"ticker": "KXMVENFLSINGLEGAME", "title": "x"}) == "NFL"
    assert league_for_series({"ticker": "KXNCAAFGAME", "title": "x"}) == "CFB"
    assert league_for_series({"ticker": "KXNBAGAME", "title": "x"}) == "NBA"
    assert league_for_series({"ticker": "KXWNBAGAME", "title": "WNBA Game", "category": "Sports"}) is None
    assert league_for_series({"ticker": "KXFOO", "title": "English Premier League winner", "category": "Sports"}) == "EPL"
    assert league_for_series({"ticker": "KXFOO", "title": "NFL ratings", "category": "Entertainment"}) is None
    assert len(LEAGUES) == 10


def test_classify():
    assert classify("KXNFLGAME") == "moneyline"
    assert classify("KXNFLSPREAD") == "spread"
    assert classify("KXNBATOTAL") == "total"
    assert classify("KXNFLPASSYDS") == "prop"
    assert classify("KXNBAREB") == "prop"
    assert classify("KXMVENFLSINGLEGAME") == "combo"
    assert classify("KXSB") == "future"
    assert classify("KXNBAEAST") == "future"
    assert classify("KXMLSCUP") == "future"
    assert classify("KXNEW", "Will Josh Allen throw for 250+ yards?") == "prop"
    assert classify("KXNEW", "Chiefs vs Bills winner") == "moneyline"
    assert classify("KXNEW", "Something unrelated") == "other"


def test_parse_event_ticker():
    assert parse_event_ticker("KXNFLGAME-25SEP07DALPHI") == (date(2025, 9, 7), "DALPHI")
    assert parse_event_ticker("KXEPLGAME-26OCT181500ARSCFC") == (date(2026, 10, 18), "ARSCFC")
    assert parse_event_ticker("KXSB-27") == (None, None)
    assert parse_event_ticker("KXNFLGAME-25FOO07DALPHI") == (None, None)


def test_split_teams_code():
    codes = {"DAL", "PHI", "KC", "BUF", "LA", "LAC", "LAL", "CLA"}
    assert split_teams_code("DALPHI", codes) == ("DAL", "PHI")
    assert split_teams_code("KCBUF", codes) == ("KC", "BUF")
    assert split_teams_code("LACLAL", codes) == ("LAC", "LAL")
    assert split_teams_code("ABCDE", {"AB", "ABC", "CDE", "DE"}) is None  # two valid splits: ambiguous
    assert split_teams_code("DALNYJ", codes) is None  # unknown code
