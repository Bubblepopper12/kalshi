"""Settings read from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_KALSHI_API_BASE = "https://external-api.kalshi.com/trade-api/v2"

# Trading hosts. Demo is Kalshi's practice exchange (play money, separate account and keys).
KALSHI_TRADING_HOSTS = {
    "demo": "https://demo-api.kalshi.co/trade-api/v2",
    "live": "https://api.elections.kalshi.com/trade-api/v2",
}


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///picks.db"
    kalshi_api_base: str = DEFAULT_KALSHI_API_BASE
    kalshi_requests_per_second: float = 8.0
    kalshi_fee_rate: float = 0.07
    kalshi_fee_contracts: int = 100

    # Trading (see trading/). Demo unless KALSHI_ENV=live is set on purpose.
    kalshi_env: str = "demo"
    kalshi_trading_base: str | None = None  # override the host for kalshi_env
    kalshi_api_key_id: str | None = None
    kalshi_private_key_path: str | None = None
    max_order_dollars: float = 10.0
    max_daily_dollars: float = 50.0
    max_contracts_per_order: int = 100
    max_open_orders: int = 5
    min_price: float = 0.03
    max_price: float = 0.95
    ticket_ttl_minutes: int = 30
    order_expiry_minutes: int = 15

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        return cls(
            database_url=env.get("PICKS_DATABASE_URL", cls.database_url),
            kalshi_api_base=env.get("KALSHI_API_BASE", cls.kalshi_api_base).rstrip("/"),
            kalshi_requests_per_second=float(
                env.get("KALSHI_REQUESTS_PER_SECOND", cls.kalshi_requests_per_second)
            ),
            kalshi_fee_rate=float(env.get("KALSHI_FEE_RATE", cls.kalshi_fee_rate)),
            kalshi_fee_contracts=int(env.get("KALSHI_FEE_CONTRACTS", cls.kalshi_fee_contracts)),
            kalshi_env=env.get("KALSHI_ENV", cls.kalshi_env).strip().lower(),
            kalshi_trading_base=env.get("KALSHI_TRADING_BASE") or None,
            kalshi_api_key_id=env.get("KALSHI_API_KEY_ID") or None,
            kalshi_private_key_path=env.get("KALSHI_PRIVATE_KEY_PATH") or None,
            max_order_dollars=float(env.get("PICKS_MAX_ORDER_DOLLARS", cls.max_order_dollars)),
            max_daily_dollars=float(env.get("PICKS_MAX_DAILY_DOLLARS", cls.max_daily_dollars)),
            max_contracts_per_order=int(env.get("PICKS_MAX_CONTRACTS_PER_ORDER", cls.max_contracts_per_order)),
            max_open_orders=int(env.get("PICKS_MAX_OPEN_ORDERS", cls.max_open_orders)),
            min_price=float(env.get("PICKS_MIN_PRICE", cls.min_price)),
            max_price=float(env.get("PICKS_MAX_PRICE", cls.max_price)),
            ticket_ttl_minutes=int(env.get("PICKS_TICKET_TTL_MINUTES", cls.ticket_ttl_minutes)),
            order_expiry_minutes=int(env.get("PICKS_ORDER_EXPIRY_MINUTES", cls.order_expiry_minutes)),
        )
