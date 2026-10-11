"""Approval-only order workflow.

The bot never decides to trade on its own. A trade goes through these steps:

1. propose   A ticket is drafted (from a board pick or by hand): market, side,
             contracts, the most it may pay. Nothing is sent to Kalshi.
2. approve   A person approves that exact ticket (CLI: type the ticker back;
             board: tick "I approve this exact order"). Tickets not approved
             within PICKS_TICKET_TTL_MINUTES expire.
3. checks    Right before sending: not halted, ticket made for this environment,
             price/size/cost limits, today's spend limit, open-order limit and
             account balance. Any failure stops the order.
4. submit    One limit buy at the approved price or better, expiring after
             PICKS_ORDER_EXPIRY_MINUTES. Every request and reply goes to trade_audit.

There is no code path that creates and submits a ticket in one step, and no
setting that turns approval off.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_UP, Decimal

import httpx
import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from ..config import Settings
from ..db import schema as t
from ..pricing.fees import kalshi_fee
from .client import KalshiAPIError, KalshiTradingClient

LIVE_STATUSES = ("submitted", "resting", "unknown")  # may still fill
SPENT_STATUSES = ("submitted", "resting", "executed", "unknown", "canceled")


class TradeRefused(Exception):
    """A ticket can't be created or sent. The message says why, in plain words."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _audit(conn: Connection, order_id: int | None, event: str, detail: dict | None = None) -> None:
    conn.execute(t.trade_audit.insert().values(order_id=order_id, ts=utcnow(), event=event, detail=detail or {}))


def max_cost(count: int, price: Decimal, fee_rate: float) -> Decimal:
    fee = Decimal(str(kalshi_fee(float(price), count, fee_rate)))
    return (count * price + fee).quantize(Decimal("0.01"), rounding=ROUND_UP)


@dataclass(frozen=True)
class Ticket:
    id: int
    env: str
    market_ticker: str
    side: str
    count: int
    limit_price: Decimal
    max_cost: Decimal
    status: str
    reason: str | None
    expires_at: datetime
    suggestion_id: int | None
    client_order_id: str
    kalshi_order_id: str | None
    fill_count: int

    def summary(self) -> str:
        return (
            f"Ticket #{self.id} [{self.env.upper()}]: BUY {self.count} {self.side.upper()} on {self.market_ticker}\n"
            f"  pay at most {self.limit_price * 100:.0f}¢ each; most this can cost: ${self.max_cost} (incl. fee)\n"
            f"  status: {self.status}; approve before {self.expires_at:%Y-%m-%d %H:%M} UTC"
            + (f"\n  why: {self.reason}" if self.reason else "")
        )


def get_ticket(conn: Connection, ticket_id: int) -> Ticket:
    row = conn.execute(sa.select(t.trade_orders).where(t.trade_orders.c.id == ticket_id)).mappings().first()
    if row is None:
        raise TradeRefused(f"There is no ticket #{ticket_id}.")
    return Ticket(
        id=row["id"], env=row["env"], market_ticker=row["market_ticker"], side=row["side"],
        count=row["count"], limit_price=Decimal(str(row["limit_price"])), max_cost=Decimal(str(row["max_cost"])),
        status=row["status"], reason=row["reason"], expires_at=_aware(row["expires_at"]),
        suggestion_id=row["suggestion_id"], client_order_id=row["client_order_id"],
        kalshi_order_id=row["kalshi_order_id"], fill_count=row["fill_count"] or 0,
    )


# ---------------------------------------------------------------- halt switch


def is_halted(conn: Connection) -> tuple[bool, str | None]:
    row = conn.execute(sa.select(t.trading_state).where(t.trading_state.c.id == 1)).mappings().first()
    return (bool(row["halted"]), row["reason"]) if row else (False, None)


def set_halt(engine: Engine, halted: bool, reason: str | None = None) -> None:
    with engine.begin() as conn:
        exists = conn.execute(sa.select(t.trading_state.c.id).where(t.trading_state.c.id == 1)).first()
        values = {"halted": halted, "reason": reason, "updated_at": utcnow()}
        if exists:
            conn.execute(t.trading_state.update().where(t.trading_state.c.id == 1).values(**values))
        else:
            conn.execute(t.trading_state.insert().values(id=1, **values))
        _audit(conn, None, "halt" if halted else "resume", {"reason": reason})


# ---------------------------------------------------------------- limits


def _static_checks(settings: Settings, count: int, price: Decimal, cost: Decimal) -> list[str]:
    problems = []
    if count < 1:
        problems.append("Contracts must be at least 1.")
    if count > settings.max_contracts_per_order:
        problems.append(f"{count} contracts is over the {settings.max_contracts_per_order}-contract limit per order.")
    if not Decimal(str(settings.min_price)) <= price <= Decimal(str(settings.max_price)):
        problems.append(f"Price {price * 100:.0f}¢ is outside the allowed {settings.min_price * 100:.0f}¢–"
                        f"{settings.max_price * 100:.0f}¢ range.")
    if price * 100 != (price * 100).to_integral_value():
        problems.append("Price must be a whole number of cents.")
    if cost > Decimal(str(settings.max_order_dollars)):
        problems.append(f"This order could cost ${cost}, over the ${settings.max_order_dollars:.2f} per-order limit.")
    return problems


def spent_today(conn: Connection, env: str) -> Decimal:
    """Most money that orders sent today (UTC) could have used. Canceled orders count only what filled."""
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    o = t.trade_orders
    rows = conn.execute(
        sa.select(o.c.status, o.c.max_cost, o.c.count, o.c.fill_count, o.c.limit_price)
        .where(o.c.env == env, o.c.submitted_at >= start, o.c.status.in_(SPENT_STATUSES))
    ).all()
    total = Decimal(0)
    for r in rows:
        if r.status == "canceled":
            total += Decimal(r.fill_count or 0) * Decimal(str(r.limit_price))
        else:
            total += Decimal(str(r.max_cost))
    return total


def open_order_count(conn: Connection, env: str) -> int:
    o = t.trade_orders
    return conn.execute(
        sa.select(sa.func.count()).where(o.c.env == env, o.c.status.in_(LIVE_STATUSES))
    ).scalar()


# ---------------------------------------------------------------- steps


def propose(engine: Engine, settings: Settings, *, ticker: str, side: str, count: int, price: float | Decimal,
            reason: str | None = None, suggestion_id: int | None = None) -> Ticket:
    """Draft a ticket. Sends nothing."""
    side = side.lower()
    if side not in ("yes", "no"):
        raise TradeRefused("Side must be YES or NO.")
    price = Decimal(str(price)).quantize(Decimal("0.0001"))
    cost = max_cost(count, price, settings.kalshi_fee_rate)
    problems = _static_checks(settings, count, price, cost)
    if problems:
        raise TradeRefused(" ".join(problems))
    now = utcnow()
    with engine.begin() as conn:
        ticket_id = conn.execute(t.trade_orders.insert().values(
            env=settings.kalshi_env, suggestion_id=suggestion_id, market_ticker=ticker.strip().upper(),
            side=side, action="buy", count=count, limit_price=price, max_cost=cost, reason=reason,
            status="proposed", client_order_id=str(uuid.uuid4()), created_at=now,
            expires_at=now + timedelta(minutes=settings.ticket_ttl_minutes),
        )).inserted_primary_key[0]
        _audit(conn, ticket_id, "proposed", {"ticker": ticker, "side": side, "count": count,
                                             "price": str(price), "max_cost": str(cost), "reason": reason})
        return get_ticket(conn, ticket_id)


def reject(engine: Engine, ticket_id: int, note: str | None = None) -> Ticket:
    with engine.begin() as conn:
        ticket = get_ticket(conn, ticket_id)
        if ticket.status != "proposed":
            raise TradeRefused(f"Ticket #{ticket_id} is {ticket.status}; only proposed tickets can be rejected.")
        conn.execute(t.trade_orders.update().where(t.trade_orders.c.id == ticket_id).values(status="rejected"))
        _audit(conn, ticket_id, "rejected", {"note": note})
        return get_ticket(conn, ticket_id)


def expire_stale(engine: Engine) -> int:
    o = t.trade_orders
    with engine.begin() as conn:
        stale = conn.execute(sa.select(o.c.id).where(o.c.status == "proposed", o.c.expires_at < utcnow())).scalars().all()
        for ticket_id in stale:
            conn.execute(o.update().where(o.c.id == ticket_id).values(status="expired"))
            _audit(conn, ticket_id, "expired")
    return len(stale)


def approve_and_submit(engine: Engine, settings: Settings, client: KalshiTradingClient, ticket_id: int, *,
                       confirm_ticker: str, via: str) -> Ticket:
    """Send one approved ticket to Kalshi after every check passes."""
    o = t.trade_orders
    with engine.begin() as conn:
        ticket = get_ticket(conn, ticket_id)
        if ticket.status != "proposed":
            raise TradeRefused(f"Ticket #{ticket_id} is {ticket.status}, not waiting for approval.")
        if confirm_ticker.strip().upper() != ticket.market_ticker:
            raise TradeRefused("The confirmation didn't match the ticket's market, so nothing was sent.")
        if ticket.expires_at < utcnow():
            conn.execute(o.update().where(o.c.id == ticket_id).values(status="expired"))
            _audit(conn, ticket_id, "expired")
            raise TradeRefused(f"Ticket #{ticket_id} expired at {ticket.expires_at:%H:%M} UTC. Make a new one.")
        if ticket.env != settings.kalshi_env or client.env != settings.kalshi_env:
            raise TradeRefused(f"Ticket #{ticket_id} was made for {ticket.env.upper()}, but the bot is set to "
                               f"{settings.kalshi_env.upper()}. Make a new ticket.")
        halted, why = is_halted(conn)
        if halted:
            raise TradeRefused(f"Trading is halted ({why or 'no reason given'}). Run `picks trade resume` first.")
        problems = _static_checks(settings, ticket.count, ticket.limit_price, ticket.max_cost)
        spent = spent_today(conn, ticket.env)
        if spent + ticket.max_cost > Decimal(str(settings.max_daily_dollars)):
            problems.append(f"Today's orders could already cost ${spent}; this one would pass the "
                            f"${settings.max_daily_dollars:.2f} daily limit.")
        if open_order_count(conn, ticket.env) >= settings.max_open_orders:
            problems.append(f"There are already {settings.max_open_orders} open orders (the limit).")
        if problems:
            _audit(conn, ticket_id, "blocked", {"problems": problems})
            raise TradeRefused(" ".join(problems))

    try:
        balance = client.balance_dollars()
    except (KalshiAPIError, httpx.HTTPError) as exc:
        raise TradeRefused(f"Couldn't read the account balance, so nothing was sent: {exc}") from exc
    if balance < ticket.max_cost:
        raise TradeRefused(f"The {ticket.env} account has ${balance}; this order could cost ${ticket.max_cost}.")

    now = utcnow()
    expiration = int((now + timedelta(minutes=settings.order_expiry_minutes)).timestamp()) \
        if settings.order_expiry_minutes > 0 else None
    with engine.begin() as conn:
        # Claim the ticket so a double click can't send it twice.
        claimed = conn.execute(
            o.update().where(o.c.id == ticket_id, o.c.status == "proposed")
            .values(status="submitted", approved_at=now, approved_via=via, submitted_at=now)
        ).rowcount
        if claimed != 1:
            raise TradeRefused(f"Ticket #{ticket_id} was already handled.")
        request = {"ticker": ticket.market_ticker, "side": ticket.side, "count": ticket.count,
                   "price": str(ticket.limit_price), "client_order_id": ticket.client_order_id,
                   "expiration_ts": expiration, "balance_before": str(balance), "via": via}
        _audit(conn, ticket_id, "submit_request", request)

    try:
        response = client.create_limit_buy(
            ticker=ticket.market_ticker, side=ticket.side, count=ticket.count, price=ticket.limit_price,
            client_order_id=ticket.client_order_id, expiration_ts=expiration,
        )
    except KalshiAPIError as exc:  # Kalshi said no: nothing was placed
        with engine.begin() as conn:
            conn.execute(o.update().where(o.c.id == ticket_id).values(status="failed", error=str(exc)))
            _audit(conn, ticket_id, "submit_rejected", {"status": exc.status, "body": exc.body})
        raise TradeRefused(f"Kalshi rejected the order: {exc}") from exc
    except httpx.HTTPError as exc:  # we don't know if it arrived
        with engine.begin() as conn:
            conn.execute(o.update().where(o.c.id == ticket_id).values(status="unknown", error=repr(exc)))
            _audit(conn, ticket_id, "submit_unknown", {"error": repr(exc)})
        raise TradeRefused("The connection dropped while sending. The order may or may not be on Kalshi; "
                           "run `picks trade refresh` before doing anything else.") from exc

    with engine.begin() as conn:
        _apply_order_state(conn, ticket_id, response.get("order") or {}, ticket.count)
        _audit(conn, ticket_id, "submit_response", response)
        if ticket.suggestion_id:
            conn.execute(t.logan_decisions.insert().values(
                suggestion_id=ticket.suggestion_id, decision="took", price_paid=ticket.limit_price,
                contracts=ticket.count, note=f"bot ticket #{ticket_id} ({ticket.env})", decided_at=utcnow(),
            ))
        return get_ticket(conn, ticket_id)


def _apply_order_state(conn: Connection, ticket_id: int, order: dict, count: int) -> None:
    status = (order.get("status") or "submitted").lower()
    status = {"cancelled": "canceled", "pending": "submitted"}.get(status, status)
    fill = order.get("fill_count")
    if fill is None and order.get("remaining_count") is not None:
        fill = count - int(order["remaining_count"])
    values = {"status": status}
    if order.get("order_id"):
        values["kalshi_order_id"] = order["order_id"]
    if fill is not None:
        values["fill_count"] = int(fill)
    conn.execute(t.trade_orders.update().where(t.trade_orders.c.id == ticket_id).values(**values))


def cancel(engine: Engine, client: KalshiTradingClient, ticket_id: int) -> Ticket:
    with engine.connect() as conn:
        ticket = get_ticket(conn, ticket_id)
    if ticket.status not in ("submitted", "resting") or not ticket.kalshi_order_id:
        raise TradeRefused(f"Ticket #{ticket_id} is {ticket.status}; there is no resting order to cancel.")
    response = client.cancel(ticket.kalshi_order_id)
    with engine.begin() as conn:
        _apply_order_state(conn, ticket_id, response.get("order") or {"status": "canceled"}, ticket.count)
        _audit(conn, ticket_id, "canceled", response)
        return get_ticket(conn, ticket_id)


def refresh(engine: Engine, client: KalshiTradingClient) -> int:
    """Update status and fills of every order that might still change."""
    o = t.trade_orders
    with engine.connect() as conn:
        ids = conn.execute(sa.select(o.c.id).where(o.c.status.in_(LIVE_STATUSES), o.c.env == client.env)).scalars().all()
    updated = 0
    for ticket_id in ids:
        with engine.connect() as conn:
            ticket = get_ticket(conn, ticket_id)
        if ticket.kalshi_order_id:
            order = client.order(ticket.kalshi_order_id)
        else:  # submit outcome unknown: look for our client_order_id
            order = next((x for x in client.orders(status=None)
                          if x.get("client_order_id") == ticket.client_order_id), None)
            if order is None:
                with engine.begin() as conn:
                    conn.execute(o.update().where(o.c.id == ticket_id).values(status="failed",
                                                                             error="not found on Kalshi"))
                    _audit(conn, ticket_id, "refresh_not_found")
                updated += 1
                continue
        with engine.begin() as conn:
            _apply_order_state(conn, ticket_id, order, ticket.count)
            _audit(conn, ticket_id, "refresh", {"status": order.get("status"), "fill_count": order.get("fill_count")})
        updated += 1
    return updated


def list_tickets(engine: Engine, statuses: list[str] | None = None, limit: int = 50) -> list[Ticket]:
    o = t.trade_orders
    q = sa.select(o.c.id).order_by(o.c.id.desc()).limit(limit)
    if statuses:
        q = q.where(o.c.status.in_(statuses))
    with engine.connect() as conn:
        return [get_ticket(conn, i) for i in conn.execute(q).scalars()]
