"""Pick board (Streamlit). Run with:  picks board   (or: streamlit run src/picks_engine/board/app.py)

The board only reads the warehouse and records Logan's Took it / Pass calls.
It has no Kalshi credentials and cannot place trades.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from picks_engine.board import queries
from picks_engine.config import Settings
from picks_engine.db import get_engine, init_db
from picks_engine.kalshi.leagues import LEAGUES
from picks_engine.picks.store import record_decision
from picks_engine.trading import orders as tr

st.set_page_config(page_title="Kalshi Picks Board", layout="wide")


@st.cache_resource
def engine():
    eng = get_engine(Settings.from_env().database_url)
    init_db(eng)
    return eng


def md(text: str) -> str:
    """Escape $ so Streamlit doesn't read "$5 ... $10" as a math formula."""
    return str(text).replace("$", "\\$")


def cents(x) -> str:
    return "" if x is None else f"{float(x) * 100:.0f}¢"


def tipster_summary(backings) -> str:
    counts: dict[str, int] = {}
    for b in backings or []:
        counts[b["tier"]] = counts.get(b["tier"], 0) + 1
    order = ["proven", "promising", "neutral", "fade"]
    return ", ".join(f"{counts[t]} {t.title()}" for t in order if t in counts) or "0"


eng = engine()
settings = Settings.from_env()
keys_set = bool(settings.kalshi_api_key_id and settings.kalshi_private_key_path)
if settings.kalshi_env == "live":
    st.error("LIVE trading: approved orders spend real money.")
else:
    st.caption("Trading environment: DEMO (practice money on demo.kalshi.co)")

with st.sidebar:
    st.header("Filters")
    leagues = st.multiselect("League", list(LEAGUES), default=["NFL"])
    pick_types = st.multiselect("Pick type", ["moneyline", "spread", "total", "prop", "combo"])
    min_edge = st.slider("Minimum edge (points)", 0.0, 15.0, 3.0, 0.5) / 100
    proven_only = st.checkbox("Proven tipsters only")
    window_h = st.slider("Games starting within (hours)", 1, 240, 48)
    st.header("Bankroll")
    bankroll = st.number_input("Bankroll ($) for the stake guide", min_value=0.0, value=1000.0, step=100.0)
    st.metric("Reported exposure today", md(f"${queries.exposure_today(eng):,.2f}"))

tab_board, tab_orders, tab_markets, tab_report = st.tabs(["Pick board", "Orders", "Kalshi markets", "Weekly report"])

with tab_board:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    rows = queries.board(
        eng, since, leagues=leagues or None, pick_types=pick_types or None, min_edge=min_edge,
        proven_only=proven_only, start_before=datetime.now(timezone.utc) + timedelta(hours=window_h),
    )
    if not rows:
        st.info("No picks on the board. Suggestions appear after the morning and pre-game runs.")
    else:
        table = pd.DataFrame([{
            "Game": r["game_label"],
            "Pick": r["description"],
            "Type": r["pick_type"],
            "Kalshi price": cents(r["kalshi_price"]),
            "Fair price": cents(r["fair_prob"]),
            "Edge": f"+{float(r['edge']) * 100:.1f}",
            "Tipsters for / against": f"{tipster_summary(r['tipsters_for'])} / {tipster_summary(r['tipsters_against'])}",
            "Model": "Agrees" if r["model_prob"] is not None else "",
            "Stake guide": f"{float(r['stake_pct'] or 0) * 100:.1f}% (${float(r['stake_pct'] or 0) * bankroll:,.0f})",
            "Decision": r["decision"] or "",
        } for r in rows])
        st.dataframe(table, use_container_width=True, hide_index=True)

        for r in rows:
            label = f"{r['game_label']} — {r['description']}  (+{float(r['edge']) * 100:.1f})"
            with st.expander(label):
                st.markdown(f"[Open on Kalshi](https://kalshi.com/markets/{r['market_ticker'].split('-')[0].lower()}) · `{r['market_ticker']}` · side **{r['side'].upper()}**")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Model", cents(r["model_prob"]))
                c2.metric("Sportsbooks (no vig)", cents(r["market_prob"]))
                c3.metric("Blend", cents(r["fair_prob"]))
                c4.metric("Depth at price", f"{r['depth_at_price'] or 0} contracts")
                st.caption(f"Kalshi ask {cents(r['kalshi_price'])} + fee {float(r['fee_per_contract']) * 100:.2f}¢")
                for title, key in (("Tipsters for", "tipsters_for"), ("Tipsters against", "tipsters_against")):
                    backers = r[key] or []
                    if backers:
                        st.markdown(f"**{title}**")
                        st.table(pd.DataFrame([{
                            "Tipster": b["name"], "Tier": b["tier"], "Record": b.get("record", ""),
                            "Posted": b.get("posted_at", ""),
                        } for b in backers]))
                notes = (r["notes"] or {}).get("injuries")
                if notes:
                    st.markdown("**Injury and lineup notes**")
                    for n in notes:
                        st.write("• " + n)
                with st.form(f"ticket-{r['id']}"):
                    st.markdown("**Make an order ticket** (nothing is sent until you approve it in Orders)")
                    tc1, tc2 = st.columns(2)
                    t_price = tc1.number_input("Most to pay (¢)", 1, 99, int(round(float(r["kalshi_price"]) * 100)),
                                               key=f"tp-{r['id']}")
                    t_count = tc2.number_input("Contracts", 1, 100000, 1, key=f"tc-{r['id']}")
                    if st.form_submit_button("Create ticket"):
                        try:
                            tk = tr.propose(eng, settings, ticker=r["market_ticker"], side=r["side"],
                                            count=int(t_count), price=t_price / 100, suggestion_id=r["id"],
                                            reason=f"Board pick #{r['id']}: {r['description']} "
                                                   f"(edge +{float(r['edge']) * 100:.1f})")
                            st.success(f"Ticket #{tk.id} created. Review it in the Orders tab.")
                        except tr.TradeRefused as exc:
                            st.error(md(str(exc)))
                if r["decision"]:
                    st.success(f"Recorded: {r['decision']}")
                else:
                    with st.form(f"decide-{r['id']}"):
                        price = st.number_input("Price paid (¢)", 1, 99, int(round(float(r["kalshi_price"]) * 100)))
                        contracts = st.number_input("Contracts", 0, 100000, 0)
                        took, passed = st.columns(2)
                        if took.form_submit_button("Took it"):
                            if contracts <= 0:
                                st.error("Enter how many contracts you bought.")
                            else:
                                record_decision(eng, r["id"], "took", price / 100, int(contracts))
                                st.rerun()
                        if passed.form_submit_button("Pass"):
                            record_decision(eng, r["id"], "pass")
                            st.rerun()

with tab_orders:
    tr.expire_stale(eng)
    with eng.connect() as conn:
        halted, why = tr.is_halted(conn)
        spent = tr.spent_today(conn, settings.kalshi_env)
    c1, c2, c3 = st.columns(3)
    c1.metric("Environment", settings.kalshi_env.upper())
    c2.metric("Committed today", md(f"${spent} of ${settings.max_daily_dollars:.0f}"))
    c3.metric("Trading", "HALTED" if halted else "On (approval needed)")
    if halted:
        st.warning(md(f"Halted: {why or ''}"))
        if st.button("Resume trading"):
            tr.set_halt(eng, False)
            st.rerun()
    elif st.button("Halt all trading"):
        tr.set_halt(eng, True, "halted from the board")
        st.rerun()
    if not keys_set:
        st.info("Kalshi keys aren't set, so tickets can be made but not sent. See the README: 'Trading setup'.")

    st.subheader("Waiting for your approval")
    waiting = tr.list_tickets(eng, ["proposed"])
    if not waiting:
        st.caption("No tickets. Make one from a pick card, or with `picks trade propose`.")
    for tk in waiting:
        with st.container(border=True):
            st.text(tk.summary())
            ok = st.checkbox(md(f"I approve this exact order: buy {tk.count} {tk.side.upper()} at up to "
                                f"{tk.limit_price * 100:.0f}¢ (max ${tk.max_cost})"), key=f"ok-{tk.id}")
            b1, b2 = st.columns(2)
            if b1.button("Send to Kalshi", key=f"send-{tk.id}", disabled=not (ok and keys_set and not halted)):
                try:
                    from picks_engine.trading.client import KalshiTradingClient

                    with KalshiTradingClient.from_settings(settings) as client:
                        done = tr.approve_and_submit(eng, settings, client, tk.id,
                                                     confirm_ticker=tk.market_ticker, via="board")
                    st.success(md(f"Sent: {done.status}, filled {done.fill_count}/{done.count}"))
                except Exception as exc:  # show every refusal or error in plain words
                    st.error(md(str(exc)))
            if b2.button("Reject", key=f"rej-{tk.id}"):
                tr.reject(eng, tk.id, "rejected on the board")
                st.rerun()

    st.subheader("Open and recent orders")
    sent = [x for x in tr.list_tickets(eng, None, limit=30) if x.status != "proposed"]
    if keys_set and st.button("Refresh order status"):
        from picks_engine.trading.client import KalshiTradingClient

        with KalshiTradingClient.from_settings(settings) as client:
            tr.refresh(eng, client)
        st.rerun()
    if sent:
        st.dataframe(pd.DataFrame([{
            "#": x.id, "Env": x.env, "Market": x.market_ticker, "Side": x.side, "Contracts": x.count,
            "Filled": x.fill_count, "Limit": f"{x.limit_price * 100:.0f}¢", "Max cost": f"${x.max_cost}",
            "Status": x.status,
        } for x in sent]), use_container_width=True, hide_index=True)
        cancellable = [x for x in sent if x.status in ("submitted", "resting") and x.kalshi_order_id]
        if cancellable and keys_set:
            pick = st.selectbox("Cancel a resting order", [f"#{x.id} {x.market_ticker}" for x in cancellable])
            if st.button("Cancel order"):
                from picks_engine.trading.client import KalshiTradingClient

                with KalshiTradingClient.from_settings(settings) as client:
                    tr.cancel(eng, client, int(pick.split()[0][1:]))
                st.rerun()

with tab_markets:
    league = st.selectbox("League", list(LEAGUES), index=0)
    mrows = queries.markets_with_prices(eng, league)
    st.caption(f"{len(mrows)} open markets with a price snapshot in the last 24 hours")
    if mrows:
        st.dataframe(pd.DataFrame([{
            "Market": r["title"], "Outcome": r["yes_sub_title"], "Type": r["market_type"],
            "Yes bid": cents(r["yes_bid"]), "Yes ask": cents(r["yes_ask"]),
            "No ask": cents(r["no_ask"]), "Volume": r["volume"], "Closes": r["close_time"],
            "Ticker": r["ticker"], "Snapshot": r["ts"],
        } for r in mrows]), use_container_width=True, hide_index=True)

with tab_report:
    end = datetime.now(timezone.utc)
    report = queries.weekly_report(eng, end - timedelta(days=7), end)
    st.subheader("Last 7 days")
    lines = [{"Who": "Board (1 contract each)", **report["board"]},
             {"Who": "Logan", **report["logan"]}]
    lines += [{"Who": f"Tipsters: {tier}", **rec} for tier, rec in report["tiers"].items()]
    st.table(pd.DataFrame(lines))
