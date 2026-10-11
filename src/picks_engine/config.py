"""Settings read from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_KALSHI_API_BASE = "https://external-api.kalshi.com/trade-api/v2"


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///picks.db"
    kalshi_api_base: str = DEFAULT_KALSHI_API_BASE
    kalshi_requests_per_second: float = 8.0
    kalshi_fee_rate: float = 0.07
    kalshi_fee_contracts: int = 100

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
        )
