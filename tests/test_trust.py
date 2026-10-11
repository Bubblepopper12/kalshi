import random
from datetime import datetime, timedelta, timezone

from picks_engine.scoring.trust import GradedPick, ScoringParams, score_tipsters

NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)


def picks_for(tid, n, win_rate, clv, seed, days_ago=10):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        win = rng.random() < win_rate
        out.append(GradedPick(tid, "NFL", "spread", NOW - timedelta(days=days_ago + i % 30),
                              "win" if win else "loss", 1.0, 0.9091 if win else -1.0,
                              clv + rng.gauss(0, 0.02)))
    return out


def test_tiers():
    picks = []
    picks += picks_for(1, 600, 0.58, 0.025, 1)   # sharp, big sample
    picks += picks_for(2, 60, 0.62, 0.02, 2)     # good but small sample
    picks += picks_for(3, 500, 0.44, -0.03, 3)   # reliably negative CLV
    for tid in range(4, 14):                      # the crowd
        picks += picks_for(tid, 400, 0.50, 0.0, tid)
    scores = {s.tipster_id: s for s in score_tipsters(picks, now=NOW)}
    assert scores[1].tier == "proven"
    assert scores[2].tier == "promising"
    assert scores[3].tier == "fade"
    assert scores[1].trust > scores[5].trust > scores[3].trust
    assert scores[1].record.startswith(str(scores[1].wins))


def test_shrinkage_and_recency():
    small = picks_for(1, 20, 0.8, 0.0, 1)
    s = score_tipsters(small, now=NOW)[0]
    assert abs(s.roi_shrunk) < abs(s.roi_observed) * 0.1  # 20 / (20 + 200)
    old = picks_for(2, 300, 0.6, 0.0, 2, days_ago=3 * 365)
    o = score_tipsters(old, now=NOW)[0]
    assert o.n_effective < 300  # spread of ages shrinks the effective sample a little
    params = ScoringParams(half_life_days=30)
    o2 = score_tipsters(old, params, now=NOW)[0]
    assert o2.n_graded == 300


def test_groups_are_separate():
    a = picks_for(1, 50, 0.6, 0.02, 1)
    b = [GradedPick(1, "NBA", "prop", p.graded_at, p.result, 1.0, p.units_won, p.clv) for p in a]
    scores = score_tipsters(a + b, now=NOW)
    assert {(s.league, s.pick_type) for s in scores} == {("NFL", "spread"), ("NBA", "prop")}
    assert all(s.trust == 0 for s in scores)  # alone in its group: no z-score
