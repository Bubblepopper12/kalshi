"""Warehouse schema (SQLAlchemy Core).

Runs on Postgres + TimescaleDB in production and on SQLite for tests and quick
local tries. The two high-volume time series (odds_snapshots and
kalshi_price_snapshots) become Timescale hypertables on Postgres; see
db/session.py.

Prices are stored as probabilities/dollars between 0 and 1 (a 54 cent Kalshi
contract is 0.54). Sportsbook prices are stored as American odds.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

metadata = sa.MetaData()

# BIGINT autoincrement on Postgres, INTEGER on SQLite (needed for ROWID autoincrement).
BigId = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
Json = sa.JSON().with_variant(JSONB(), "postgresql")
Ts = sa.DateTime(timezone=True)
Prob = sa.Numeric(6, 4)


def _now():
    return sa.func.now()


# ---------------------------------------------------------------- reference data

teams = sa.Table(
    "teams",
    metadata,
    sa.Column("id", BigId, primary_key=True, autoincrement=True),
    sa.Column("league", sa.String(16), nullable=False),
    sa.Column("name", sa.String(128), nullable=False),
    sa.Column("abbreviation", sa.String(16)),
    sa.UniqueConstraint("league", "name"),
)

players = sa.Table(
    "players",
    metadata,
    sa.Column("id", BigId, primary_key=True, autoincrement=True),
    sa.Column("league", sa.String(16), nullable=False),
    sa.Column("name", sa.String(128), nullable=False),
    sa.Column("team_id", sa.ForeignKey("teams.id")),
    sa.Column("position", sa.String(16)),
)

games = sa.Table(
    "games",
    metadata,
    sa.Column("id", BigId, primary_key=True, autoincrement=True),
    sa.Column("league", sa.String(16), nullable=False),
    sa.Column("season", sa.Integer),
    sa.Column("week", sa.Integer),
    sa.Column("home_team_id", sa.ForeignKey("teams.id"), nullable=False),
    sa.Column("away_team_id", sa.ForeignKey("teams.id"), nullable=False),
    sa.Column("start_time", Ts, nullable=False),
    sa.Column("neutral_site", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("status", sa.String(16), nullable=False, server_default="scheduled"),
    sa.Column("home_score", sa.Integer),
    sa.Column("away_score", sa.Integer),
    sa.Index("ix_games_league_start", "league", "start_time"),
)

# ID matching: every source names teams, players, games and markets differently.
# One row maps (entity_type, source, source_key) to our internal id.
entity_aliases = sa.Table(
    "entity_aliases",
    metadata,
    sa.Column("id", BigId, primary_key=True, autoincrement=True),
    sa.Column("entity_type", sa.String(16), nullable=False),  # team | player | game
    sa.Column("league", sa.String(16), nullable=False),
    sa.Column("source", sa.String(64), nullable=False),  # kalshi | odds_api | covers | ...
    sa.Column("source_key", sa.String(256), nullable=False),
    sa.Column("internal_id", sa.BigInteger, nullable=False),
    sa.Column("method", sa.String(16), nullable=False, server_default="manual"),
    sa.Column("created_at", Ts, nullable=False, server_default=_now()),
    sa.UniqueConstraint("entity_type", "league", "source", "source_key"),
)

# Misses from automatic matching wait here for a human.
id_review_queue = sa.Table(
    "id_review_queue",
    metadata,
    sa.Column("id", BigId, primary_key=True, autoincrement=True),
    sa.Column("entity_type", sa.String(16), nullable=False),
    sa.Column("league", sa.String(16), nullable=False),
    sa.Column("source", sa.String(64), nullable=False),
    sa.Column("source_key", sa.String(256), nullable=False),
    sa.Column("context", Json),
    sa.Column("status", sa.String(16), nullable=False, server_default="open"),
    sa.Column("resolved_internal_id", sa.BigInteger),
    sa.Column("created_at", Ts, nullable=False, server_default=_now()),
    sa.Column("resolved_at", Ts),
    sa.UniqueConstraint("entity_type", "league", "source", "source_key"),
)

# ---------------------------------------------------------------- stats and results

plays = sa.Table(
    "plays",
    metadata,
    sa.Column("game_id", sa.ForeignKey("games.id"), primary_key=True),
    sa.Column("sequence", sa.Integer, primary_key=True),
    sa.Column("league", sa.String(16), nullable=False),
    sa.Column("period", sa.Integer),
    sa.Column("clock", sa.String(16)),
    sa.Column("description", sa.Text),
    sa.Column("data", Json),
)

player_game_stats = sa.Table(
    "player_game_stats",
    metadata,
    sa.Column("player_id", sa.ForeignKey("players.id"), primary_key=True),
    sa.Column("game_id", sa.ForeignKey("games.id"), primary_key=True),
    sa.Column("league", sa.String(16), nullable=False),
    sa.Column("minutes_or_snaps", sa.Numeric(8, 2)),
    sa.Column("stats", Json, nullable=False),  # {"pass_yds": 287, "pass_td": 2, ...}
)

# ---------------------------------------------------------------- sportsbook odds

# One book's price on one outcome at one moment. Hypertable on ts.
odds_snapshots = sa.Table(
    "odds_snapshots",
    metadata,
    sa.Column("ts", Ts, primary_key=True),
    sa.Column("game_id", sa.ForeignKey("games.id"), primary_key=True),
    sa.Column("book", sa.String(32), primary_key=True),
    sa.Column("market", sa.String(48), primary_key=True),  # h2h | spreads | totals | player_pass_yds ...
    sa.Column("outcome", sa.String(16), primary_key=True),  # home | away | draw | over | under
    sa.Column("participant", sa.String(64), primary_key=True, server_default=""),  # player id for props
    sa.Column("line", sa.Numeric(8, 2)),
    sa.Column("price_american", sa.Integer, nullable=False),
    sa.Column("is_closing", sa.Boolean, nullable=False, server_default=sa.false()),
)

# ---------------------------------------------------------------- Kalshi

kalshi_series = sa.Table(
    "kalshi_series",
    metadata,
    sa.Column("ticker", sa.String(64), primary_key=True),
    sa.Column("league", sa.String(16)),
    sa.Column("title", sa.String(256)),
    sa.Column("category", sa.String(64)),
    sa.Column("frequency", sa.String(32)),
    sa.Column("tags", Json),
    sa.Column("market_type", sa.String(16)),  # see kalshi/classify.py
    sa.Column("synced_at", Ts, nullable=False, server_default=_now()),
)

kalshi_events = sa.Table(
    "kalshi_events",
    metadata,
    sa.Column("ticker", sa.String(96), primary_key=True),
    sa.Column("series_ticker", sa.String(64), nullable=False),
    sa.Column("league", sa.String(16)),
    sa.Column("title", sa.String(256)),
    sa.Column("sub_title", sa.String(256)),
    sa.Column("game_date", sa.Date),  # parsed from the ticker when possible
    sa.Column("teams_code", sa.String(16)),  # e.g. "DALPHI" from KXNFLGAME-25SEP04DALPHI
    sa.Column("game_id", sa.ForeignKey("games.id")),
    sa.Column("synced_at", Ts, nullable=False, server_default=_now()),
)

kalshi_markets = sa.Table(
    "kalshi_markets",
    metadata,
    sa.Column("ticker", sa.String(128), primary_key=True),
    sa.Column("event_ticker", sa.String(96), nullable=False),
    sa.Column("series_ticker", sa.String(64), nullable=False),
    sa.Column("league", sa.String(16)),
    sa.Column("market_type", sa.String(16)),  # moneyline | spread | total | prop | combo | future | other
    sa.Column("title", sa.String(512)),
    sa.Column("yes_sub_title", sa.String(256)),
    sa.Column("no_sub_title", sa.String(256)),
    sa.Column("status", sa.String(16)),
    sa.Column("open_time", Ts),
    sa.Column("close_time", Ts),
    sa.Column("expiration_time", Ts),
    sa.Column("result", sa.String(16)),  # yes | no | "" while open
    sa.Column("rules_primary", sa.Text),
    sa.Column("rules_secondary", sa.Text),
    sa.Column("game_id", sa.ForeignKey("games.id")),
    sa.Column("first_seen_at", Ts, nullable=False, server_default=_now()),
    sa.Column("last_synced_at", Ts, nullable=False, server_default=_now()),
    sa.Column("raw", Json),
    sa.Index("ix_kalshi_markets_league_status", "league", "status"),
    sa.Index("ix_kalshi_markets_event", "event_ticker"),
)

# One Kalshi market's top of book at one moment. Hypertable on ts.
kalshi_price_snapshots = sa.Table(
    "kalshi_price_snapshots",
    metadata,
    sa.Column("market_ticker", sa.String(128), primary_key=True),
    sa.Column("ts", Ts, primary_key=True),
    sa.Column("yes_bid", Prob),
    sa.Column("yes_ask", Prob),
    sa.Column("no_bid", Prob),
    sa.Column("no_ask", Prob),
    sa.Column("last_price", Prob),
    sa.Column("volume", sa.BigInteger),
    sa.Column("volume_24h", sa.BigInteger),
    sa.Column("open_interest", sa.BigInteger),
)

# Full order book, only for markets that matter (board candidates). Levels are
# [[price, quantity], ...] bids for each side, as Kalshi returns them.
kalshi_orderbook_snapshots = sa.Table(
    "kalshi_orderbook_snapshots",
    metadata,
    sa.Column("market_ticker", sa.String(128), primary_key=True),
    sa.Column("ts", Ts, primary_key=True),
    sa.Column("yes_bids", Json, nullable=False),
    sa.Column("no_bids", Json, nullable=False),
)

# ---------------------------------------------------------------- tipsters and picks

tipsters = sa.Table(
    "tipsters",
    metadata,
    sa.Column("id", BigId, primary_key=True, autoincrement=True),
    sa.Column("source", sa.String(64), nullable=False),  # action_network | covers | x | reddit ...
    sa.Column("handle", sa.String(128), nullable=False),
    sa.Column("display_name", sa.String(128)),
    sa.Column("url", sa.String(512)),
    sa.Column("created_at", Ts, nullable=False, server_default=_now()),
    sa.UniqueConstraint("source", "handle"),
)

picks = sa.Table(
    "picks",
    metadata,
    sa.Column("id", BigId, primary_key=True, autoincrement=True),
    sa.Column("tipster_id", sa.ForeignKey("tipsters.id"), nullable=False),
    sa.Column("league", sa.String(16), nullable=False),
    sa.Column("game_id", sa.ForeignKey("games.id")),
    sa.Column("pick_type", sa.String(16), nullable=False),  # moneyline | spread | total | prop | combo
    sa.Column("market", sa.String(48)),  # matches odds_snapshots.market, e.g. player_rec_yds
    sa.Column("side", sa.String(16), nullable=False),  # home | away | draw | over | under
    sa.Column("participant", sa.String(64), nullable=False, server_default=""),
    sa.Column("line", sa.Numeric(8, 2)),
    sa.Column("price_american", sa.Integer),
    sa.Column("units", sa.Numeric(8, 2), nullable=False, server_default="1"),
    sa.Column("posted_at", Ts),  # when the tipster says it was posted
    sa.Column("captured_at", Ts, nullable=False),  # when we saw it
    sa.Column("gradable", sa.Boolean, nullable=False, server_default=sa.true()),
    sa.Column("source_url", sa.String(512)),
    sa.Column("raw", Json),
    sa.Index("ix_picks_tipster", "tipster_id"),
    sa.Index("ix_picks_game", "game_id"),
)

pick_grades = sa.Table(
    "pick_grades",
    metadata,
    sa.Column("pick_id", sa.ForeignKey("picks.id"), primary_key=True),
    sa.Column("result", sa.String(8), nullable=False),  # win | loss | push | void
    sa.Column("units_risked", sa.Numeric(10, 4), nullable=False),
    sa.Column("units_won", sa.Numeric(10, 4), nullable=False),
    sa.Column("closing_price_american", sa.Integer),
    sa.Column("clv", sa.Numeric(8, 5)),  # closing fair prob - posted implied prob
    sa.Column("graded_at", Ts, nullable=False, server_default=_now()),
)

# Scores per tipster, league and pick type (e.g. NBA / prop).
tipster_scores = sa.Table(
    "tipster_scores",
    metadata,
    sa.Column("tipster_id", sa.ForeignKey("tipsters.id"), primary_key=True),
    sa.Column("league", sa.String(16), primary_key=True),
    sa.Column("pick_type", sa.String(16), primary_key=True),
    sa.Column("n_graded", sa.Integer, nullable=False),
    sa.Column("n_effective", sa.Numeric(10, 2), nullable=False),
    sa.Column("clv_mean", sa.Numeric(8, 5)),
    sa.Column("clv_t", sa.Numeric(8, 3)),
    sa.Column("roi_observed", sa.Numeric(8, 5)),
    sa.Column("roi_shrunk", sa.Numeric(8, 5)),
    sa.Column("trust", sa.Numeric(8, 4), nullable=False),
    sa.Column("tier", sa.String(16), nullable=False),  # proven | promising | neutral | fade
    sa.Column("record", sa.String(32)),  # "312-260-9"
    sa.Column("computed_at", Ts, nullable=False, server_default=_now()),
)

# ---------------------------------------------------------------- board

suggestions = sa.Table(
    "suggestions",
    metadata,
    sa.Column("id", BigId, primary_key=True, autoincrement=True),
    sa.Column("run_id", sa.String(64), nullable=False),
    sa.Column("created_at", Ts, nullable=False, server_default=_now()),
    sa.Column("league", sa.String(16), nullable=False),
    sa.Column("game_id", sa.ForeignKey("games.id")),
    sa.Column("game_label", sa.String(256)),
    sa.Column("game_start", Ts),
    sa.Column("market_ticker", sa.String(128), nullable=False),
    sa.Column("side", sa.String(4), nullable=False),  # yes | no
    sa.Column("pick_type", sa.String(16), nullable=False),
    sa.Column("description", sa.String(512), nullable=False),
    sa.Column("kalshi_price", Prob, nullable=False),  # ask for the chosen side
    sa.Column("fee_per_contract", Prob, nullable=False),
    sa.Column("fair_prob", Prob, nullable=False),
    sa.Column("edge", Prob, nullable=False),  # fair - (price + fee)
    sa.Column("model_prob", Prob),
    sa.Column("market_prob", Prob),
    sa.Column("tipster_prob", Prob),
    sa.Column("tipsters_for", Json),
    sa.Column("tipsters_against", Json),
    sa.Column("depth_at_price", sa.Integer),
    sa.Column("stake_pct", sa.Numeric(6, 4)),
    sa.Column("notes", Json),
    sa.Index("ix_suggestions_created", "created_at"),
)

logan_decisions = sa.Table(
    "logan_decisions",
    metadata,
    sa.Column("id", BigId, primary_key=True, autoincrement=True),
    sa.Column("suggestion_id", sa.ForeignKey("suggestions.id"), nullable=False),
    sa.Column("decision", sa.String(8), nullable=False),  # took | pass
    sa.Column("price_paid", Prob),
    sa.Column("contracts", sa.Integer),
    sa.Column("note", sa.Text),
    sa.Column("decided_at", Ts, nullable=False, server_default=_now()),
)

# ---------------------------------------------------------------- trading (approval-only)

# One order ticket. Nothing reaches Kalshi until a ticket is approved by a person;
# see trading/orders.py for the lifecycle:
#   proposed -> approved+submitted -> resting | executed | canceled
#   proposed -> rejected | expired;  submit errors -> failed
trade_orders = sa.Table(
    "trade_orders",
    metadata,
    sa.Column("id", BigId, primary_key=True, autoincrement=True),
    sa.Column("env", sa.String(8), nullable=False),  # demo | live
    sa.Column("suggestion_id", sa.ForeignKey("suggestions.id")),
    sa.Column("market_ticker", sa.String(128), nullable=False),
    sa.Column("side", sa.String(4), nullable=False),  # yes | no
    sa.Column("action", sa.String(4), nullable=False, server_default="buy"),
    sa.Column("count", sa.Integer, nullable=False),
    sa.Column("limit_price", Prob, nullable=False),  # most we will pay per contract
    sa.Column("max_cost", sa.Numeric(12, 2), nullable=False),  # count * price + fee
    sa.Column("reason", sa.Text),  # why this ticket exists (pick, note)
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("client_order_id", sa.String(64), nullable=False, unique=True),
    sa.Column("kalshi_order_id", sa.String(64)),
    sa.Column("fill_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("created_at", Ts, nullable=False),
    sa.Column("expires_at", Ts, nullable=False),  # unapproved tickets die after this
    sa.Column("approved_at", Ts),
    sa.Column("approved_via", sa.String(32)),  # cli | board
    sa.Column("submitted_at", Ts),
    sa.Column("error", sa.Text),
    sa.Index("ix_trade_orders_status", "status"),
)

# Every step of every ticket, including the exact request and Kalshi's reply.
trade_audit = sa.Table(
    "trade_audit",
    metadata,
    sa.Column("id", BigId, primary_key=True, autoincrement=True),
    sa.Column("order_id", sa.ForeignKey("trade_orders.id")),
    sa.Column("ts", Ts, nullable=False),
    sa.Column("event", sa.String(32), nullable=False),
    sa.Column("detail", Json),
)

# Single-row switch: when halted, no order can be submitted.
trading_state = sa.Table(
    "trading_state",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("halted", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("reason", sa.Text),
    sa.Column("updated_at", Ts, nullable=False, server_default=_now()),
)

# ---------------------------------------------------------------- operations

sync_runs = sa.Table(
    "sync_runs",
    metadata,
    sa.Column("id", BigId, primary_key=True, autoincrement=True),
    sa.Column("job", sa.String(64), nullable=False),
    sa.Column("league", sa.String(16)),
    sa.Column("started_at", Ts, nullable=False),
    sa.Column("finished_at", Ts),
    sa.Column("status", sa.String(16), nullable=False),  # running | ok | failed
    sa.Column("stats", Json),
    sa.Column("error", sa.Text),
)

HYPERTABLES = {
    "odds_snapshots": "ts",
    "kalshi_price_snapshots": "ts",
    "kalshi_orderbook_snapshots": "ts",
}
