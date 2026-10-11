from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

from picks_engine.db import schema as t
from picks_engine.scoring.jobs import rescore_tipsters


def test_rescore_from_database(engine):
    start = datetime(2026, 10, 4, 17, tzinfo=timezone.utc)
    with engine.begin() as conn:
        a = conn.execute(t.teams.insert().values(league="NFL", name="A")).inserted_primary_key[0]
        b = conn.execute(t.teams.insert().values(league="NFL", name="B")).inserted_primary_key[0]
        game = conn.execute(t.games.insert().values(league="NFL", home_team_id=a, away_team_id=b,
                                                    start_time=start)).inserted_primary_key[0]
        tips = [conn.execute(t.tipsters.insert().values(source="covers", handle=h)).inserted_primary_key[0]
                for h in ("good", "bad")]
        for i in range(40):
            for tid, win, clv in ((tips[0], i % 5 != 0, 0.02), (tips[1], i % 5 == 0, -0.02)):
                pid = conn.execute(t.picks.insert().values(
                    tipster_id=tid, league="NFL", game_id=game, pick_type="spread", side="home", line=-3,
                    price_american=-110, units=1, captured_at=start - timedelta(hours=2),
                )).inserted_primary_key[0]
                conn.execute(t.pick_grades.insert().values(
                    pick_id=pid, result="win" if win else "loss", units_risked=1,
                    units_won=0.9091 if win else -1, clv=clv))
        # A pick seen after kickoff is stored but never scored.
        late = conn.execute(t.picks.insert().values(
            tipster_id=tips[1], league="NFL", game_id=game, pick_type="spread", side="home", line=-3,
            units=1, captured_at=start + timedelta(minutes=5), gradable=False)).inserted_primary_key[0]
        conn.execute(t.pick_grades.insert().values(pick_id=late, result="win", units_risked=1, units_won=0.9))

    assert rescore_tipsters(engine) == 2
    with engine.connect() as conn:
        rows = {r.tipster_id: r for r in conn.execute(sa.select(t.tipster_scores))}
    assert rows[tips[0]].trust > 0 > rows[tips[1]].trust
    assert rows[tips[0]].tier == "promising"
    assert rows[tips[1]].n_graded == 40 and rows[tips[0]].record == "32-8-0"
