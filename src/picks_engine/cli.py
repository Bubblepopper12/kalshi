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


# ---------------------------------------------------------------- trading (approval-only)


def _trading_client(settings):
    from .trading.client import KalshiTradingClient

    return KalshiTradingClient.from_settings(settings)


def _env_banner(settings) -> str:
    if settings.kalshi_env == "live":
        return "LIVE — REAL MONEY"
    return "DEMO — practice money (demo.kalshi.co)"


def cmd_trade(args, settings):
    from decimal import Decimal

    import sqlalchemy as sa

    import httpx

    from .db import schema as t
    from .trading import orders as tr
    from .trading.client import KalshiAPIError, TradingNotConfigured

    engine = _engine(settings)
    tr.expire_stale(engine)
    action = args.trade_command

    try:
        if action == "status":
            with engine.connect() as conn:
                halted, why = tr.is_halted(conn)
                spent = tr.spent_today(conn, settings.kalshi_env)
                open_n = tr.open_order_count(conn, settings.kalshi_env)
            print(f"Environment:   {_env_banner(settings)}")
            print(f"Trading:       {'HALTED (' + (why or '') + ')' if halted else 'allowed with approval'}")
            print(f"Keys set:      {'yes' if settings.kalshi_api_key_id and settings.kalshi_private_key_path else 'no'}")
            print(f"Limits:        ${settings.max_order_dollars:.2f}/order, ${settings.max_daily_dollars:.2f}/day, "
                  f"{settings.max_contracts_per_order} contracts/order, {settings.max_open_orders} open orders, "
                  f"price {settings.min_price * 100:.0f}¢–{settings.max_price * 100:.0f}¢")
            print(f"Today:         ${spent} committed, {open_n} open orders")
            return

        if action == "propose":
            if args.suggestion:
                with engine.connect() as conn:
                    s = conn.execute(sa.select(t.suggestions).where(t.suggestions.c.id == args.suggestion)).mappings().first()
                if s is None:
                    raise tr.TradeRefused(f"There is no board pick #{args.suggestion}.")
                ticker, side = s["market_ticker"], s["side"]
                price = Decimal(args.price) / 100 if args.price else Decimal(str(s["kalshi_price"]))
                reason = args.reason or f"Board pick #{s['id']}: {s['description']} (edge +{float(s['edge']) * 100:.1f})"
            else:
                if not (args.ticker and args.side and args.price):
                    raise tr.TradeRefused("Give --suggestion ID, or all of --ticker, --side and --price.")
                ticker, side, price, reason = args.ticker, args.side, Decimal(args.price) / 100, args.reason
            ticket = tr.propose(engine, settings, ticker=ticker, side=side, count=args.contracts, price=price,
                                reason=reason, suggestion_id=args.suggestion)
            print(ticket.summary())
            print(f"\nNothing has been sent. To send it: picks trade approve {ticket.id}")
            return

        if action == "list":
            tickets = tr.list_tickets(engine, None if args.all else ["proposed", *tr.LIVE_STATUSES])
            if not tickets:
                print("No tickets." if args.all else "No tickets waiting or open. Use --all to see history.")
            for tk in tickets:
                print(tk.summary() + (f"\n  filled: {tk.fill_count}/{tk.count}" if tk.status != "proposed" else ""))
                print()
            return

        if action == "approve":
            with engine.connect() as conn:
                ticket = tr.get_ticket(conn, args.id)
            print(f"[{_env_banner(settings)}]\n")
            print(ticket.summary())
            if ticket.status != "proposed":
                raise tr.TradeRefused(f"Ticket #{ticket.id} is {ticket.status}, not waiting for approval.")
            client = _trading_client(settings)  # fails here, before asking, if keys aren't set up
            if settings.kalshi_env == "live":
                print("\nThis will spend REAL MONEY from your Kalshi account.")
            try:
                typed = input(f"\nType the market ticker ({ticket.market_ticker}) to send this order, "
                              "or press Enter to cancel: ")
            except EOFError:
                typed = ""
            with client:
                if not typed.strip():
                    print("Not sent.")
                    return
                ticket = tr.approve_and_submit(engine, settings, client, args.id, confirm_ticker=typed, via="cli")
            print(f"\nSent. Kalshi order {ticket.kalshi_order_id}: {ticket.status}, filled {ticket.fill_count}/{ticket.count}")
            return

        if action == "reject":
            print(tr.reject(engine, args.id, args.note).summary())
            return

        if action == "cancel":
            with _trading_client(settings) as client:
                print(tr.cancel(engine, client, args.id).summary())
            return

        if action == "refresh":
            with _trading_client(settings) as client:
                print(f"{tr.refresh(engine, client)} orders updated")
            return

        if action == "balance":
            with _trading_client(settings) as client:
                print(f"[{_env_banner(settings)}] balance: ${client.balance_dollars()}")
            return

        if action == "positions":
            with _trading_client(settings) as client:
                rows = client.positions()
            print(f"[{_env_banner(settings)}]")
            for p in rows:
                if p.get("position"):
                    print(f"  {p.get('ticker')}: {p.get('position')} contracts "
                          f"(exposure {p.get('market_exposure_dollars') or p.get('market_exposure')})")
            if not any(p.get("position") for p in rows):
                print("  no open positions")
            return

        if action == "halt":
            tr.set_halt(engine, True, args.reason or "halted from the command line")
            print("Trading halted. No order can be sent until `picks trade resume`.")
            return

        if action == "resume":
            tr.set_halt(engine, False)
            print("Trading resumed. Every order still needs your approval.")
            return

        if action == "log":
            with engine.connect() as conn:
                rows = conn.execute(sa.select(t.trade_audit).where(t.trade_audit.c.order_id == args.id)
                                    .order_by(t.trade_audit.c.id)).mappings().all()
            for r in rows:
                print(f"{r['ts']}  {r['event']:<16} {json.dumps(r['detail'], default=str)}")
            return
    except (tr.TradeRefused, TradingNotConfigured, KalshiAPIError, FileNotFoundError, PermissionError,
            ValueError) as exc:
        raise SystemExit(f"Not done: {exc}") from None
    except httpx.HTTPError as exc:
        raise SystemExit(f"Not done: couldn't reach Kalshi ({exc!r}). Run `picks trade refresh` once it's back.") from None


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

    tp = sub.add_parser("trade", help="approval-only trading (demo by default); see `picks trade -h`")
    ts = tp.add_subparsers(dest="trade_command", required=True)
    ts.add_parser("status", help="environment, halt switch, limits and today's spend")
    pr = ts.add_parser("propose", help="draft an order ticket (sends nothing)")
    pr.add_argument("--suggestion", type=int, help="board pick id to trade")
    pr.add_argument("--ticker", help="Kalshi market ticker (manual ticket)")
    pr.add_argument("--side", choices=["yes", "no"])
    pr.add_argument("--price", type=int, help="most to pay per contract, in cents")
    pr.add_argument("--contracts", type=int, required=True)
    pr.add_argument("--reason", help="note saved with the ticket")
    ls_ = ts.add_parser("list", help="tickets waiting for approval and open orders")
    ls_.add_argument("--all", action="store_true")
    for name, helptext in (("approve", "review a ticket and send it (asks you to type the ticker)"),
                           ("cancel", "cancel a resting order"), ("log", "full audit trail of a ticket")):
        x = ts.add_parser(name, help=helptext)
        x.add_argument("id", type=int)
    rj = ts.add_parser("reject", help="throw a ticket away")
    rj.add_argument("id", type=int)
    rj.add_argument("--note")
    ts.add_parser("refresh", help="update status and fills of open orders")
    ts.add_parser("balance", help="account balance")
    ts.add_parser("positions", help="open positions")
    h = ts.add_parser("halt", help="stop all order sending immediately")
    h.add_argument("reason", nargs="?")
    ts.add_parser("resume", help="allow approved orders again")
    tp.set_defaults(func=cmd_trade)

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
