import pytest

from picks_engine.picks import Backing, BlendParams, Candidate, build_board, combo_probability, evaluate
from picks_engine.picks.generate import blend, tipster_signal


def cand(**kw):
    base = dict(market_ticker="KXNFLGAME-26OCT18DALPHI-PHI", league="NFL", pick_type="moneyline",
                description_yes="Eagles to win", description_no="Cowboys to win",
                yes_ask=0.54, no_ask=0.47, model_prob=0.61, market_prob=0.59,
                depth_yes=500, depth_no=500)
    return Candidate(**(base | kw))


PROVEN = [Backing(f"sharp{i}", "proven", 1.5, True) for i in range(3)]


def test_concept_example_reaches_board():
    s = evaluate(cand(backings=PROVEN))
    assert s is not None and s.side == "yes" and s.description == "Eagles to win"
    assert s.fair_prob > 0.60
    assert s.edge == pytest.approx(s.fair_prob - 0.54 - 0.0174, abs=1e-4)
    assert 0 < s.stake_pct <= 0.02
    assert len(s.tipsters_for) == 3 and not s.tipsters_against


def test_filters():
    assert evaluate(cand(model_prob=0.55, market_prob=0.56)) is None          # under 3 points
    assert evaluate(cand(depth_yes=20)) is None                                # thin book
    assert evaluate(cand(injury_unconfirmed=True)) is None                     # injury pending
    assert evaluate(cand(model_prob=0.50)) is None                             # model disagrees
    assert evaluate(cand(model_prob=None)) is None                             # missing view
    against = [Backing("sharp", "proven", 2.0, False)]
    assert evaluate(cand(backings=against)) is None                            # tipsters disagree


def test_no_side_is_checked():
    s = evaluate(cand(model_prob=0.40, market_prob=0.41, no_ask=0.52))
    assert s.side == "no" and s.description == "Cowboys to win"
    assert s.model_prob == pytest.approx(0.60)


def test_fade_counts_the_other_way():
    p = BlendParams()
    assert tipster_signal([Backing("bad", "fade", 1.0, True)], p) < 0
    assert tipster_signal([Backing("bad", "fade", 1.0, False)], p) > 0
    assert tipster_signal([Backing("meh", "neutral", 1.0, True)], p) == 0
    assert tipster_signal([], p) is None


def test_blend_skips_missing_views():
    p = BlendParams()
    assert blend(0.6, None, None, p) == pytest.approx(0.6)
    assert 0.55 < blend(0.6, 0.55, None, p) < 0.6


def test_board_sorted_by_edge():
    a = cand(market_ticker="A", model_prob=0.62, market_prob=0.60)
    b = cand(market_ticker="B", model_prob=0.70, market_prob=0.68)
    c = cand(market_ticker="C", model_prob=0.5, market_prob=0.5)
    assert [s.market_ticker for s in build_board([a, b, c])] == ["B", "A"]


def test_combo_correlation():
    indep = combo_probability([0.6, 0.55])
    assert indep.joint_prob == pytest.approx(0.33, abs=0.005)
    pos = combo_probability([0.6, 0.55], [[1, 0.5], [0.5, 1]])
    assert pos.joint_prob > indep.joint_prob + 0.05
    with pytest.raises(ValueError):
        combo_probability([0.5] * 5)
