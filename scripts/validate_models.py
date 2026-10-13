"""Check the pricing models against reality before trusting them.

1. Soccer backtest: for every game in football-data's archives (5 leagues, several seasons), fit the
   goals model to Pinnacle's closing 1X2 and over/under 2.5 odds, predict other markets (over 1.5,
   3.5, 4.5, both teams score, home/away win by 2+), and compare the average prediction with how
   often it actually happened. A good model matches within ~1 point on every market.
2. Kalshi ladders: for every open game, fit the same model to Kalshi's own winner prices and its
   middle over/under line, then see how far the model sits from Kalshi's prices on the other lines.

Read-only; needs internet (run on GitHub: Actions -> Validate models).
"""

from __future__ import annotations

import csv
import io
import statistics
import sys
from collections import defaultdict

import httpx

sys.path.insert(0, "src")
from picks_engine.kalshi.client import KalshiReadOnlyClient, price_field  # noqa: E402
from picks_engine.kalshi.leagues import LEAGUES, game_series  # noqa: E402
from picks_engine.live.lines import parse_line  # noqa: E402
from picks_engine.pricing.devig import devig  # noqa: E402
from picks_engine import pricing  # noqa: E402,F401
from picks_engine.pricing import models  # noqa: E402

SEASONS = ["1920", "2021", "2122", "2223", "2324", "2425", "2526"]
DIVS = {"E0": "EPL", "SP1": "LaLiga", "I1": "SerieA", "D1": "Bundesliga", "F1": "Ligue1"}


def american(d: float) -> float:
    return (d - 1) * 100 if d >= 2 else -100 / (d - 1)


def soccer_backtest() -> None:
    preds: dict[str, list[tuple[float, int]]] = defaultdict(list)
    n_games = 0
    for season in SEASONS:
        for div in DIVS:
            url = f"https://www.football-data.co.uk/mmz4281/{season}/{div}.csv"
            try:
                text = httpx.get(url, timeout=60, follow_redirects=True).content.decode("utf-8-sig", "replace")
            except httpx.HTTPError as exc:
                print("skip", url, exc)
                continue
            for r in csv.DictReader(io.StringIO(text)):
                try:
                    hg, ag = int(r["FTHG"]), int(r["FTAG"])
                    h, d, a = (float(r[k]) for k in ("PSCH", "PSCD", "PSCA"))
                    o, u = float(r.get("PC>2.5") or r.get("AvgC>2.5")), float(r.get("PC<2.5") or r.get("AvgC<2.5"))
                except (KeyError, ValueError, TypeError):
                    continue
                ph, pd, pa = devig([american(h), american(d), american(a)])
                po, _ = devig([american(o), american(u)])
                m = models.fit_soccer(ph, pd, pa, 2.5, po)
                n_games += 1
                tot = hg + ag
                for name, p, hit in (
                    ("over 1.5", m.total_over(1.5), tot > 1.5), ("over 2.5 (fitted)", m.total_over(2.5), tot > 2.5),
                    ("over 3.5", m.total_over(3.5), tot > 3.5), ("over 4.5", m.total_over(4.5), tot > 4.5),
                    ("both score", m.both_score(), hg > 0 and ag > 0), ("draw", m.draw(), hg == ag),
                    ("home by 2+", m.wins_by_more_than("home", 1.5), hg - ag > 1.5),
                    ("away by 2+", m.wins_by_more_than("away", 1.5), ag - hg > 1.5),
                    ("home by 3+", m.wins_by_more_than("home", 2.5), hg - ag > 2.5),
                ):
                    preds[name].append((p, int(hit)))
    print(f"\n=== Soccer model vs results: {n_games} games ===")
    print(f"{'market':<20}{'model':>8}{'actual':>8}{'gap pts':>9}")
    for name, xs in preds.items():
        mp = statistics.mean(p for p, _ in xs) * 100
        ac = statistics.mean(h for _, h in xs) * 100
        print(f"{name:<20}{mp:8.1f}{ac:8.1f}{ac - mp:+9.1f}")
    # calibration by bucket for over 3.5 and both score
    for name in ("over 3.5", "both score", "home by 2+"):
        print(f"\n{name} by predicted chance:")
        buckets = defaultdict(list)
        for p, h in preds[name]:
            buckets[min(int(p * 10), 9)].append((p, h))
        for b in sorted(buckets):
            xs = buckets[b]
            print(f"  {b * 10:>2}-{b * 10 + 10:<3}% n={len(xs):5d} model {statistics.mean(p for p, _ in xs) * 100:5.1f} "
                  f"actual {statistics.mean(h for _, h in xs) * 100:5.1f}")


def mid(m: dict) -> float | None:
    b, a = price_field(m, "yes_bid"), price_field(m, "yes_ask")
    if b is None or a is None or not (0 < a <= 1) or a - b > 0.06 or b <= 0:
        return None
    return float((a + b) / 2)


def kalshi_ladders() -> None:
    gaps: dict[tuple[str, str], list[float]] = defaultdict(list)
    with KalshiReadOnlyClient(requests_per_second=8) as rc:
        series = rc.series(category="Sports")
        for code, lg in LEAGUES.items():
            ev = {}
            for kind in ("moneyline", "total", "spread", "btts"):
                for sr in game_series(lg, series, kind):
                    for e in rc.events(sr["ticker"], status="open", with_nested_markets=True):
                        ev.setdefault(e["event_ticker"].split("-", 1)[1], {})[kind] = e.get("markets") or []
            for key, kinds in ev.items():
                winners = kinds.get("moneyline") or []
                totals = [(parse_line(m, "total") or {}).get("line") for m in kinds.get("total") or []]
                tmids = {ln: mid(m) for ln, m in zip(totals, kinds.get("total") or []) if ln is not None}
                tmids = {k: v for k, v in tmids.items() if v is not None}
                if not winners or not tmids:
                    continue
                center = min(tmids, key=lambda ln: abs(tmids[ln] - 0.5))
                wm = {m["ticker"].rsplit("-", 1)[-1]: mid(m) for m in winners}
                if any(v is None for v in wm.values()):
                    continue
                codes = [k for k in wm if k not in ("TIE", "DRAW")]
                if lg.sport == "soccer":
                    tie = next((v for k, v in wm.items() if k in ("TIE", "DRAW")), None)
                    teams = [wm[k] for k in codes]
                    if tie is None or len(teams) != 2:
                        continue
                    s = sum(teams) + tie
                    model = models.fit_soccer(teams[0] / s, tie / s, teams[1] / s, center, tmids[center])
                    btts = [mid(m) for m in kinds.get("btts") or []]
                    if btts and btts[0] is not None:
                        gaps[(code, "both score")].append((btts[0] - model.both_score()) * 100)
                else:
                    if len(wm) != 2:
                        continue
                    p = list(wm.values())
                    model = models.fit_points(code, p[0] / sum(p), None, None, center, tmids[center])
                for ln, v in tmids.items():
                    off = ln - center
                    if off == 0 or model.total_over(ln) is None:
                        continue
                    step = 1 if lg.sport == "soccer" else 4
                    band = f"total {round(off / step) * step:+g}"
                    gaps[(code, band)].append((v - model.total_over(ln)) * 100)
                for m in kinds.get("spread") or []:
                    info, v = parse_line(m, "spread"), mid(m)
                    team_code = "".join(ch for ch in m["ticker"].rsplit("-", 1)[-1] if not ch.isdigit())
                    if not info or v is None or team_code not in codes:
                        continue
                    side = "home" if team_code == codes[0] else "away"
                    p_model = model.wins_by_more_than(side, info["line"])
                    fav = (wm[team_code] or 0) >= 0.5
                    step = 1 if lg.sport == "soccer" else 4
                    gaps[(code, f"{'fav' if fav else 'dog'} by {round(info['line'] / step) * step:g}+")].append(
                        (v - p_model) * 100)
    print("\n=== Kalshi's own prices minus the model (points; + = Kalshi higher) ===")
    for (code, band), xs in sorted(gaps.items()):
        if len(xs) >= 3:
            print(f"{code:<11}{band:<22} n={len(xs):4d} mean {statistics.mean(xs):+5.1f}  "
                  f"median {statistics.median(xs):+5.1f}")


if __name__ == "__main__":
    which = sys.argv[1:] or ["soccer", "kalshi"]
    if "kalshi" in which:
        kalshi_ladders()
    if "soccer" in which:
        soccer_backtest()
