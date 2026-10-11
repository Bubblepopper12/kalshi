"""Edge of a fair probability against the Kalshi price, after fees."""

from __future__ import annotations

from dataclasses import dataclass

from .fees import fee_per_contract


@dataclass(frozen=True)
class EdgeQuote:
    price: float
    fee: float
    fair_prob: float

    @property
    def cost(self) -> float:
        return self.price + self.fee

    @property
    def edge(self) -> float:
        """Probability points of edge after the fee (0.06 = 6 points)."""
        return self.fair_prob - self.cost

    @property
    def edge_before_fees(self) -> float:
        return self.fair_prob - self.price


def quote_edge(fair_prob: float, ask: float, fee_contracts: int = 100, fee_rate: float = 0.07) -> EdgeQuote:
    return EdgeQuote(price=ask, fee=fee_per_contract(ask, fee_contracts, fee_rate), fair_prob=fair_prob)
