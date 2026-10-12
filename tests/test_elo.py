import math

import pytest

from picks_engine.models.elo import EloModel, EloParams, Game, backtest


def test_expected_score_matches_gemini_formula():
    m = EloModel(EloParams(hfa=65))
    m.ratings = {"A": 1600, "B": 1500}
    assert m.home_win_prob("A", "B") == pytest.approx(1 / (1 + 10 ** ((1500 - 1665) / 400)))
    assert m.home_win_prob("A", "B", neutral=True) == pytest.approx(1 / (1 + 10 ** (-100 / 400)))


def test_update_is_zero_sum_and_upsets_move_more():
    m = EloModel(EloParams(mov=False, k=20))
    m.ratings = {"A": 1600, "B": 1400}
    m.update(Game(2025, "A", "B", 20, 17))
    gain_fav = m.ratings["A"] - 1600
    assert m.ratings["A"] + m.ratings["B"] == pytest.approx(3000)
    m2 = EloModel(EloParams(mov=False, k=20))
    m2.ratings = {"A": 1600, "B": 1400}
    m2.update(Game(2025, "A", "B", 17, 20))
    assert 1600 - m2.ratings["A"] > gain_fav  # losing as a favourite costs more than winning gains


def test_margin_of_victory_and_season_reversion():
    m = EloModel(EloParams(k=20))
    m.update(Game(2024, "A", "B", 40, 0))
    big = m.ratings["A"] - 1505
    m2 = EloModel(EloParams(k=20))
    m2.update(Game(2024, "A", "B", 21, 20))
    assert big > m2.ratings["A"] - 1505 > 0
    m.update(Game(2025, "C", "D", None, None))  # new season: halfway back to 1505
    assert m.ratings["A"] - 1505 == pytest.approx(big / 2)


def test_backtest_scores_only_test_seasons():
    games = [Game(2024, "A", "B", 24, 10, home_moneyline=-150, away_moneyline=130),
             Game(2025, "A", "B", 10, 24, home_moneyline=-150, away_moneyline=130)]
    bt = backtest(games, {2025}, EloParams(k=20))
    assert bt.games == 1 and bt.model_log_loss > 0 and not math.isnan(bt.market_log_loss)
