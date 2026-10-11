import pytest

from picks_engine.pricing import (
    american_to_decimal, american_to_prob, devig, fee_per_contract, kalshi_fee, quote_edge, stake_fraction,
)
from picks_engine.pricing.devig import prob_to_american


def test_kalshi_fee_rounds_up_to_cent():
    assert kalshi_fee(0.54, 1) == 0.02  # 0.07 * 0.2484 = 0.0174 -> 2 cents
    assert kalshi_fee(0.54, 100) == 1.74  # 1.7388 -> 1.74
    assert kalshi_fee(0.50, 100) == 1.75  # exactly 1.75 stays 1.75
    assert fee_per_contract(0.54, 100) == pytest.approx(0.0174)


def test_odds_conversion():
    assert american_to_decimal(150) == 2.5
    assert american_to_decimal(-200) == 1.5
    assert american_to_prob(-110) == pytest.approx(0.5238, abs=1e-4)
    assert prob_to_american(0.6) == -150 and prob_to_american(0.4) == 150
    with pytest.raises(ValueError):
        american_to_decimal(50)


@pytest.mark.parametrize("method", ["multiplicative", "power"])
def test_devig_sums_to_one(method):
    two = devig([-110, -110], method)
    assert two == pytest.approx([0.5, 0.5])
    three = devig([150, 240, 190], method)
    assert sum(three) == pytest.approx(1.0)
    fav = devig([-300, 250], method)
    assert sum(fav) == pytest.approx(1.0) and fav[0] > 0.7


def test_power_devig_shades_longshot_more():
    mult, power = devig([-400, 300], "multiplicative"), devig([-400, 300], "power")
    assert power[1] < mult[1]


def test_edge_matches_concept_example():
    q = quote_edge(0.60, 0.54)
    assert q.edge_before_fees == pytest.approx(0.06)
    assert q.edge == pytest.approx(0.06 - 0.0174)


def test_stake_guide_quarter_kelly_capped():
    assert stake_fraction(0.57, 0.5574) == pytest.approx(0.25 * (0.57 - 0.5574) / (1 - 0.5574), abs=1e-4)
    assert stake_fraction(0.90, 0.50) == 0.02
    assert stake_fraction(0.50, 0.55) == 0.0
