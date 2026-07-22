import math
from typing import List, Tuple

from ..config import SDAConfig
from ..models import MarketState, Order, State
from .base import Strategy


class AdaptiveDCAStrategy(Strategy):
    """High-investment DCA strategy with drawdown-based reinforcement buys."""

    def __init__(self, cfg: SDAConfig):
        self.cfg = cfg

    def on_day(self, market_state: MarketState, portfolio_state: State) -> List[Order]:
        orders: List[Order] = []

        if market_state.is_month_start:
            monthly_amount = self.cfg.monthly_contribution * (1.0 - self.cfg.adca_reserve_pct)
            if monthly_amount >= self.cfg.min_order_eur:
                orders.append(self._build_order(market_state, monthly_amount, "MONTHLY-DCA"))

        orders.extend(self._evaluate_dip_buys(market_state, portfolio_state))
        return orders

    def _evaluate_dip_buys(self, market_state: MarketState, state: State) -> List[Order]:
        if math.isnan(market_state.drawdown):
            return []

        for threshold, tranche_eur, label in self._sorted_tiers():
            if market_state.drawdown > threshold:
                continue
            if self.cfg.adca_cooldown_days > 0 and label in state.cooldowns:
                continue

            amount_eur = min(tranche_eur, state.cash_ocf)
            if amount_eur < self.cfg.min_order_eur:
                continue

            cooldown_days = self.cfg.adca_cooldown_days if self.cfg.adca_cooldown_days > 0 else None
            return [
                self._build_order(
                    market_state,
                    amount_eur,
                    label,
                    drawdown=market_state.drawdown,
                    cooldown_days=cooldown_days,
                )
            ]

        return []

    def _sorted_tiers(self) -> List[Tuple[float, float, str]]:
        return sorted(self.cfg.adca_dip_tiers, key=lambda x: x[0])

    def _build_order(
        self,
        market_state: MarketState,
        amount: float,
        tier: str,
        drawdown: float = None,
        cooldown_days: int = None,
    ) -> Order:
        exec_price = market_state.close * (1.0 + self.cfg.slippage)
        units = amount / exec_price
        return Order(
            date=market_state.date,
            amount_eur=round(amount, 4),
            price=round(exec_price, 6),
            units=round(units, 6),
            tier=tier,
            drawdown=round(drawdown, 6) if drawdown is not None else None,
            cooldown_days=cooldown_days,
        )
