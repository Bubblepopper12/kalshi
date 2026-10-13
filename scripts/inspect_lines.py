"""Print a few live Kalshi spread / total / both-teams-to-score markets per league, and how the bot reads them.

Read-only. Used to check the line reader against Kalshi's real wording:  python scripts/inspect_lines.py
"""

from picks_engine.kalshi.client import KalshiReadOnlyClient
from picks_engine.kalshi.leagues import LEAGUES, game_series
from picks_engine.live.lines import parse_line

with KalshiReadOnlyClient(requests_per_second=8) as rc:
    series = rc.series(category="Sports")
    for code, lg in LEAGUES.items():
        for kind in ("spread", "total", "btts"):
            found = game_series(lg, series, kind)
            print(f"\n== {code} {kind}: {[s['ticker'] for s in found]}")
            shown = 0
            for sr in found:
                for ev in rc.events(sr["ticker"], status="open", with_nested_markets=True):
                    for m in (ev.get("markets") or [])[:3]:
                        print(f"  {m.get('ticker')} | sub={m.get('yes_sub_title')!r} | title={m.get('title')!r} "
                              f"| strike={m.get('floor_strike')} | ask={m.get('yes_ask_dollars') or m.get('yes_ask')} "
                              f"-> {parse_line(m, kind)}")
                    shown += 1
                    if shown >= 2:
                        break
                if shown >= 2:
                    break
    mve = [s["ticker"] for s in series if "KXMVE" in (s.get("ticker") or "")][:20]
    print("\ncombo series:", mve)
