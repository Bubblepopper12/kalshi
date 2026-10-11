from datetime import datetime, timedelta, timezone

import pytest

from picks_engine.scoring.grading import Outcome, grade, is_gradable


def test_moneyline_and_three_way():
    o = Outcome(home_score=24, away_score=20)
    assert grade("moneyline", "home", None, 150, 1, o).units_won == 1.5
    assert grade("moneyline", "away", None, -150, 2, o).units_won == -2
    tie = Outcome(home_score=1, away_score=1)
    assert grade("moneyline", "home", None, 120, 1, tie).result == "push"
    assert grade("moneyline", "home", None, 120, 1, tie, three_way=True).result == "loss"
    assert grade("moneyline", "draw", None, 230, 1, tie, three_way=True).units_won == 2.3


def test_spread_total_prop():
    o = Outcome(home_score=27, away_score=24)
    assert grade("spread", "home", -3, -110, 1, o).result == "push"
    assert grade("spread", "home", -2.5, -110, 1, o).units_won == pytest.approx(0.9091, abs=1e-4)
    assert grade("spread", "away", 3.5, -110, 1, o).result == "win"
    assert grade("total", "over", 51, -110, 1, o).result == "push"
    assert grade("total", "under", 51.5, -110, 1, o).result == "win"
    assert grade("prop", "over", 69.5, -115, 1, Outcome(stat_value=70)).result == "win"
    assert grade("prop", "under", 69.5, -115, 1, Outcome(stat_value=70)).result == "loss"
    assert grade("prop", "over", 69.5, -115, 1, Outcome(void=True)).result == "void"


def test_clv_and_missing_odds():
    g = grade("spread", "home", -3, -110, 1, Outcome(home_score=30, away_score=20), closing_fair_prob=0.56)
    assert g.clv == pytest.approx(0.56 - 0.5238, abs=1e-4)
    assert grade("spread", "home", -3, None, 1, Outcome(home_score=30, away_score=20)).clv is None


def test_gradable_only_before_kickoff():
    ko = datetime(2026, 10, 18, 17, tzinfo=timezone.utc)
    assert is_gradable(ko - timedelta(hours=3), ko - timedelta(hours=2), ko)
    assert not is_gradable(ko - timedelta(hours=3), ko + timedelta(minutes=5), ko)  # found after kickoff
    assert not is_gradable(None, ko, ko)
