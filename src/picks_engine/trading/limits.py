"""Per-order limits shared by the terminal/board workflow and the web app."""

from __future__ import annotations

from decimal import ROUND_UP, Decimal

from ..config import Settings
from ..pricing.fees import kalshi_fee


def max_cost(count: int, price: Decimal, fee_rate: float) -> Decimal:
    """Most a buy of `count` contracts at `price` can cost, including Kalshi's fee."""
    fee = Decimal(str(kalshi_fee(float(price), count, fee_rate)))
    return (count * price + fee).quantize(Decimal("0.01"), rounding=ROUND_UP)


def static_checks(settings: Settings, count: int, price: Decimal, cost: Decimal) -> list[str]:
    """Problems with one order on its own (size, price, cost). Empty list means it's within limits."""
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
