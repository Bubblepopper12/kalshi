"""`picks research`: every league in one go, with a plain-English verdict for each.

For each league: download Kalshi's price history of finished games, load the sportsbooks'
closing lines where a free source exists (NFL and the soccer leagues), run the history tests,
and write:

  research/reports/<LEAGUE>.md   the full tables for one league
  research/reports/summary.md    one page: a verdict per league, plus all leagues pooled
  research/reports/summary.json  the same, for the website's Research tab

Raw price files go to research/data/ (not committed: they're large). Each run adds only the
games that finished since the last one; GitHub keeps the files between runs in its cache.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

from . import history, reference
from .kalshi.client import KalshiReadOnlyClient
from .kalshi.leagues import LEAGUES

REPORTS = Path("research/reports")
DATA = Path("research/data")
MIN_BETS = 30  # fewer bets than this: too few to say anything
SOLID_BETS = 200  # this many before calling anything an edge
TOO_GOOD = 0.15  # +15% per bet against closing lines is not a realistic edge: flag it as a likely data problem


@dataclass
class LeagueSummary:
    code: str
    name: str
    markets: int = 0
    games: int = 0
    source: str = ""
    tag: str = ""  # edge | watch | none | few | check | kalshi-only | error
    verdict: str = ""
    points: list[str] = field(default_factory=list)
    error: str = ""
    updated: str = ""  # when this league was last run (ISO, UTC)
    buckets: list[list[float]] = field(default_factory=list)  # [low, n, price_sum, wins, pnl] for pooling
    rule3: list[float] = field(default_factory=list)  # [bets, wins, pnl] buying 3+ points under the books


def _pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def judge(code: str, report: history.Report) -> LeagueSummary:
    """Turn one league's report into a short verdict anyone can read."""
    out = LeagueSummary(code, LEAGUES[code].name, report.markets, report.games, report.source,
                        buckets=[[b.low, b.n, b.price_sum, b.wins, b.pnl] for b in report.buckets])
    if report.comparison is not None:
        r3 = report.comparison.rule(3)
        out.rule3 = [r3.bets, r3.wins, r3.pnl]
    if not report.markets:
        out.tag, out.verdict = "few", "No finished games on Kalshi in this period yet."
        return out
    c = report.comparison
    if c is not None:
        gap = c.loss_kalshi - c.loss_books
        if gap <= 0.005:
            out.points.append(f"Kalshi's pre-game prices were about as accurate as the sportsbooks' closing lines "
                              f"({c.matched} prices compared).")
        else:
            out.points.append(f"Kalshi's pre-game prices were less accurate than the sportsbooks' closing lines "
                              f"({c.matched} prices compared), so Kalshi sometimes lags the books.")
        r3 = c.rule(3)
        if r3.bets:
            out.points.append(f"Buying whenever Kalshi was 3+ points cheaper than the books: {r3.bets} bets, "
                              f"{r3.wins} won, {_pct(r3.per_bet)} per bet after fees.")
        else:
            out.points.append("Kalshi was never 3+ points cheaper than the books before a game.")
        if r3.bets >= MIN_BETS and r3.per_bet > TOO_GOOD:
            out.tag = "check"
            out.verdict = ("Needs checking: the return looks too good to be true, which usually means a data "
                           "problem rather than real money. Not trusted until it's explained.")
        elif r3.bets >= SOLID_BETS and r3.per_bet > 0.02:
            out.tag, out.verdict = "edge", "Edge found: buying when Kalshi is cheaper than the books made money."
        elif r3.bets < MIN_BETS:
            out.tag, out.verdict = "few", "Too few cheap Kalshi prices to tell yet."
        elif r3.per_bet > 0:
            out.tag, out.verdict = "watch", "Worth watching: positive so far, but not enough bets to trust."
        else:
            out.tag, out.verdict = "none", "No edge: when Kalshi looked cheaper than the books, it lost money."
    else:
        out.tag = "kalshi-only"
        out.verdict = "Kalshi-only test (no free sportsbook history for this league)."
    ls = report.longshots(20)
    if ls.bets:
        won = ls.wins / ls.bets * 100
        if ls.bets >= 100 and ls.per_bet < -0.05:
            out.points.append(f"Cheap long shots (under 20¢) lost money: {ls.bets} bets, {won:.0f}% won, "
                              f"{_pct(ls.per_bet)} per bet. Avoid them.")
        else:
            out.points.append(f"Cheap long shots (under 20¢): {ls.bets} bets, {won:.0f}% won, "
                              f"{_pct(ls.per_bet)} per bet.")
    fav = report.favorites(70)
    if fav.bets:
        out.points.append(f"Big favorites (70¢ and up): {fav.bets} bets, {fav.wins / fav.bets * 100:.0f}% won, "
                          f"{_pct(fav.per_bet)} per bet.")
    return out


def pooled(leagues: list[LeagueSummary]) -> list[str]:
    """All leagues together: bigger samples, so these numbers mean more than any single league's.

    Leagues that failed or whose numbers need checking are left out.
    """
    used = [s for s in leagues if s.buckets and s.tag not in ("error", "check")]
    if not used:
        return []
    buckets = [history.Bucket(lo, lo + 10) for lo in range(0, 100, 10)]
    for s in used:
        for b, (_, n, price_sum, wins, pnl) in zip(buckets, s.buckets):
            b.n += int(n)
            b.price_sum += price_sum
            b.wins += int(wins)
            b.pnl += pnl
    lines = ["## All leagues together", "",
             f"{sum(s.markets for s in used):,} Kalshi markets from {sum(s.games for s in used):,} games "
             f"({', '.join(s.name for s in used)}).", "",
             "| Price | Markets | Average price | Actually won | Return per bet |",
             "| --- | --- | --- | --- | --- |"] + [b.line() for b in buckets] + [""]
    rules = [s.rule3 for s in used if s.rule3]
    n, wins, pnl = int(sum(r[0] for r in rules)), int(sum(r[1] for r in rules)), sum(r[2] for r in rules)
    if rules:
        lines += [f"Buying whenever Kalshi was 3+ points cheaper than the sportsbooks' closing line, "
                  f"in every league with sportsbook data: {n} bets, {wins} won, "
                  f"{_pct(pnl / n) if n else '+0.0%'} per bet after fees.", ""]
    return lines


def _summary_markdown(results: list[LeagueSummary], pool: list[str], since: datetime) -> str:
    out = [f"# Kalshi research: all leagues ({datetime.now(timezone.utc):%b %-d, %Y})", "",
           f"Finished games since {since:%b %-d, %Y}. Every price is Kalshi's last price before the game, "
           "and every return includes Kalshi's fee.", ""]
    for s in results:
        out += [f"## {s.name}", "", f"**{s.verdict or s.error}**", ""]
        out += [f"- {p}" for p in s.points] + ([""] if s.points else [])
    return "\n".join(out + pool + [
        "Small samples swing a lot: treat fewer than ~200 bets as a hint, not proof. "
        "Past results don't promise future ones."])


def _fetch(url: str) -> str:
    resp = httpx.get(url, timeout=60, follow_redirects=True)
    resp.raise_for_status()
    return resp.content.decode("utf-8-sig", errors="replace")


def closing_lines(code: str, since: datetime, fetch: Callable[[str], str], progress) -> dict:
    """Keyword arguments for history.analyze: the league's closing lines, or {} without a source."""
    try:
        if code == "NFL":
            return {"nflverse_csv": fetch(history.NFLVERSE_GAMES), "source": "nflverse (closing moneylines)"}
        urls = reference.soccer_sources(code, since)
        if not urls:
            return {}
        games = []
        for url in urls:
            try:
                games += reference.parse_football_data(fetch(url), uk_times=code not in reference.SOCCER_EXTRA)
            except httpx.HTTPStatusError as exc:  # e.g. a season file that doesn't exist yet
                progress(f"  (no closing lines at {url}: {exc.response.status_code})")
        return {"reference": games, "source": "football-data.co.uk (Pinnacle closing odds)"}
    except httpx.HTTPError as exc:
        progress(f"  (couldn't load closing lines: {exc!r}; running the Kalshi-only tests)")
        return {}


def run(client: KalshiReadOnlyClient, leagues: list[str], since: datetime, reports: Path = REPORTS,
        data: Path = DATA, fetch: Callable[[str], str] = _fetch, fee_rate: float = 0.07,
        progress=print, reuse_data: bool = False, update: bool = True,
        on_league: Callable[[str], None] | None = None) -> list[LeagueSummary]:
    """Run the leagues one by one. Results merge into summary.json, so leagues not run this time keep
    their last results, and `on_league` (e.g. saving to GitHub) can publish each league as it finishes."""
    reports.mkdir(parents=True, exist_ok=True)
    results: list[LeagueSummary] = []
    for code in leagues:
        name = LEAGUES[code].name
        progress(f"\n=== {name} ===")
        path = data / f"kalshi_{code}_history.csv"
        try:
            if not (reuse_data and path.exists()):
                history.download(client, code, since, path, progress=progress, update=update)
        except (httpx.HTTPError, SystemExit) as exc:
            msg = str(exc) if isinstance(exc, SystemExit) else f"couldn't reach Kalshi ({exc!r})"
            progress(f"  skipped: {msg}")
            results.append(LeagueSummary(code, name, tag="error", error=f"Not loaded: {msg}"))
        else:
            report = history.analyze(path, code, fee_rate=fee_rate, **closing_lines(code, since, fetch, progress))
            (reports / f"{code}.md").write_text(report.markdown(code))
            results.append(judge(code, report))
            progress(f"  {results[-1].verdict}")
        results[-1].updated = datetime.now(timezone.utc).isoformat(timespec="seconds")
        save_summary(reports, results, since)
        if on_league:
            on_league(code)
    return results


def load_summary(reports: Path) -> dict[str, LeagueSummary]:
    try:
        data = json.loads((reports / "summary.json").read_text())
    except (OSError, ValueError):
        return {}
    known = set(LeagueSummary.__dataclass_fields__)
    return {x["code"]: LeagueSummary(**{k: v for k, v in x.items() if k in known})
            for x in data.get("leagues") or [] if x.get("code") in LEAGUES}


def save_summary(reports: Path, fresh: list[LeagueSummary], since: datetime) -> None:
    """Merge this run's leagues into the saved summary (league order as in LEAGUES)."""
    merged = load_summary(reports) | {s.code: s for s in fresh}
    ordered = [merged[c] for c in LEAGUES if c in merged]
    pool = pooled(ordered)
    (reports / "summary.md").write_text(_summary_markdown(ordered, pool, since))
    (reports / "summary.json").write_text(json.dumps({
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "since": since.date().isoformat(),
        "leagues": [asdict(r) for r in ordered],
        "pooled": pool,
    }, indent=2))
