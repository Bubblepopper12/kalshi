"""Command line: `picks <command>`. Run `picks --help` for the list."""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

from .config import Settings
from .db import get_engine, init_db
from .kalshi import KalshiReadOnlyClient
from .kalshi import sync as ks
from .kalshi.leagues import LEAGUES


def _engine(settings: Settings):
    engine = get_engine(settings.database_url)
    init_db(engine)
    return engine


def _client(settings: Settings) -> KalshiReadOnlyClient:
    return KalshiReadOnlyClient(settings.kalshi_api_base, settings.kalshi_requests_per_second)


def cmd_init_db(args, settings):
    _engine(settings)
    print(f"Schema ready at {settings.database_url}")


def cmd_leagues(args, settings):
    for lg in sorted(LEAGUES.values(), key=lambda x: (x.priority, x.code)):
        print(f"{lg.code:<11} priority {lg.priority}  {lg.season:<8} {lg.name}")


def cmd_discover(args, settings):
    with _client(settings) as client:
        from .kalshi.classify import classify

        for s in ks.discover_series(client, args.league):
            print(f"{s['ticker']:<28} {classify(s['ticker'], s.get('title') or ''):<10} {s.get('title')}")


def cmd_sync(args, settings):
    engine = _engine(settings)
    with _client(settings) as client:
        for league in args.league:
            stats = ks.sync_league(engine, client, league)
            print(f"{league}: {json.dumps(stats.as_dict())}")


def cmd_snapshot(args, settings):
    engine = _engine(settings)
    with _client(settings) as client:
        while True:
            for league in args.league:
                try:
                    stats = ks.snapshot_prices(engine, client, league)
                    print(f"{time.strftime('%H:%M:%S')} {league}: {stats.snapshots} snapshots, "
                          f"{stats.markets} new markets", flush=True)
                except Exception as exc:  # keep the loop alive; the failure is in sync_runs
                    print(f"{league}: snapshot failed: {exc!r}", file=sys.stderr, flush=True)
                    if not args.every:
                        raise
            if not args.every:
                return
            time.sleep(args.every)


def cmd_settle(args, settings):
    engine = _engine(settings)
    with _client(settings) as client:
        for league in args.league:
            print(f"{league}: {ks.refresh_settlements(engine, client, league)} markets refreshed")


def cmd_gate(args, settings):
    if args.phase != 1:
        raise SystemExit("Only the Phase 1 gate is automated so far.")
    engine = _engine(settings)
    with _client(settings) as client:
        report = ks.phase1_gate(engine, client, args.league)
    print(report.summary())
    raise SystemExit(0 if report.passed else 1)


def cmd_link(args, settings):
    from .ids.mapping import link_kalshi_events

    print(link_kalshi_events(_engine(settings), args.league))


def cmd_score(args, settings):
    from .scoring.jobs import rescore_tipsters

    print(f"{rescore_tipsters(_engine(settings))} tipster scores written")


def cmd_board(args, settings):
    app = Path(__file__).parent / "board" / "app.py"
    raise SystemExit(subprocess.call([sys.executable, "-m", "streamlit", "run", str(app), *args.streamlit_args]))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="picks", description="Kalshi Picks Engine (read-only research tool)")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="create tables (and hypertables on TimescaleDB)").set_defaults(func=cmd_init_db)
    sub.add_parser("leagues", help="list supported leagues").set_defaults(func=cmd_leagues)

    d = sub.add_parser("discover", help="show the Kalshi series that match a league right now")
    d.add_argument("league")
    d.set_defaults(func=cmd_discover)

    s = sub.add_parser("sync", help="daily listing sync: series, events, markets + one price snapshot")
    s.add_argument("league", nargs="+")
    s.set_defaults(func=cmd_sync)

    sn = sub.add_parser("snapshot", help="price snapshot of every open market (use --every 300 to loop)")
    sn.add_argument("league", nargs="+")
    sn.add_argument("--every", type=int, default=0, help="seconds between snapshots; 0 runs once")
    sn.set_defaults(func=cmd_snapshot)

    st = sub.add_parser("settle", help="refresh results of markets past their close time")
    st.add_argument("league", nargs="+")
    st.set_defaults(func=cmd_settle)

    g = sub.add_parser("gate", help="check a build-phase gate")
    g.add_argument("phase", type=int)
    g.add_argument("--league", default="NFL")
    g.set_defaults(func=cmd_gate)

    lk = sub.add_parser("link", help="attach Kalshi game events to games; misses go to the review queue")
    lk.add_argument("league")
    lk.set_defaults(func=cmd_link)

    sub.add_parser("score", help="recompute tipster trust scores and tiers").set_defaults(func=cmd_score)

    b = sub.add_parser("board", help="open the Streamlit pick board")
    b.add_argument("streamlit_args", nargs=argparse.REMAINDER)
    b.set_defaults(func=cmd_board)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args.func(args, Settings.from_env())


if __name__ == "__main__":
    main()
