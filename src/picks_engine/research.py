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


@dataclass
class LeagueSummary:
    code: str
    name: str
    markets: int = 0
    games: int = 0
    source: str = ""
    tag: str = ""  # edge | watch | none | few | kalshi-only | error
    verdict: str = ""
    points: list[str] = field(default_factory=list)
    error: str = ""


def _pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def judge(code: str, report: history.Report) -> LeagueSummary:
    """Turn one league's report into a short verdict anyone can read."""
    out = LeagueSummary(code, LEAGUES[code].name, report.markets, report.games, report.source)
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
        if r3.bets >= SOLID_BETS and r3.per_bet > 0.02:
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


def pooled(reports: list[history.Report]) -> list[str]:
    """All leagues together: bigger samples, so these numbers mean more than any single league's."""
    if not reports:
        return []
    buckets = [history.Bucket(lo, lo + 10) for lo in range(0, 100, 10)]
    for r in reports:
        for b, rb in zip(buckets, r.buckets):
            b.n += rb.n
            b.price_sum += rb.price_sum
            b.wins += rb.wins
            b.pnl += rb.pnl
    lines = ["## All leagues together", "",
             f"{sum(r.markets for r in reports)} Kalshi markets from {sum(r.games for r in reports)} games.", "",
             "| Price | Markets | Average price | Actually won | Return per bet |",
             "| --- | --- | --- | --- | --- |"] + [b.line() for b in buckets] + [""]
    rules = [r.comparison.rule(3) for r in reports if r.comparison]
    n, wins, pnl = sum(x.bets for x in rules), sum(x.wins for x in rules), sum(x.pnl for x in rules)
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
        progress=print, reuse_data: bool = False, update: bool = True) -> list[LeagueSummary]:
    reports.mkdir(parents=True, exist_ok=True)
    results: list[LeagueSummary] = []
    done: list[history.Report] = []
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
            continue
        report = history.analyze(path, code, fee_rate=fee_rate, **closing_lines(code, since, fetch, progress))
        (reports / f"{code}.md").write_text(report.markdown(code))
        done.append(report)
        results.append(judge(code, report))
        progress(f"  {results[-1].verdict}")
    pool = pooled(done)
    (reports / "summary.md").write_text(_summary_markdown(results, pool, since))
    (reports / "summary.json").write_text(json.dumps({
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "since": since.date().isoformat(),
        "leagues": [asdict(r) for r in results],
        "pooled": pool,
    }, indent=2))
    return results
