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
        monthly_orders: List[Order] = []

        if market_state.is_month_start:
            monthly_amount = self.cfg.monthly_contribution * (1.0 - self.cfg.adca_reserve_pct)
            if monthly_amount >= self.cfg.min_order_eur:
                monthly_orders.append(self._build_order(market_state, monthly_amount, "MONTHLY-DCA"))
                orders.extend(monthly_orders)

        available_cash = portfolio_state.cash_ocf
        if monthly_orders:
            available_cash = max(0.0, available_cash - sum(o.amount_eur for o in monthly_orders))

        adjusted_state = State(
            cash_ocf=available_cash,
            units=portfolio_state.units,
            portfolio_value=portfolio_state.portfolio_value,
            cooldowns=dict(portfolio_state.cooldowns),
            total_contributions=portfolio_state.total_contributions,
            total_cashflow=portfolio_state.total_cashflow,
        )

        orders.extend(self._evaluate_dip_buys(market_state, adjusted_state))
        return orders

    def _evaluate_dip_buys(self, market_state: MarketState, state: State) -> List[Order]:
        if math.isnan(market_state.drawdown):
            return []

        for threshold, tranche_eur, label in self._sorted_tiers():
            if market_state.drawdown > threshold:
                continue
            if self.cfg.adca_cooldown_days > 0 and label in state.cooldowns:
                continue

            amount_eur = self._max_affordable_amount(min(tranche_eur, state.cash_ocf), state.cash_ocf)
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

    def _max_affordable_amount(self, requested_amount: float, available_cash: float) -> float:
        """Return max order amount that still fits cash including fees for non-monthly tiers."""
        if requested_amount <= 0.0 or available_cash <= 0.0:
            return 0.0

        # For dip tiers we pay fixed+variable broker fees capped by fee cap.
        base = self.cfg.broker_base_fee_eur
        var = self.cfg.broker_variable_fee_rate
        cap = self.cfg.broker_fee_cap_eur

        if available_cash <= base:
            return 0.0

        # Uncapped regime: cash >= amount + base + var * amount
        uncapped = (available_cash - base) / (1.0 + var)
        if base + var * max(uncapped, 0.0) <= cap:
            return max(0.0, min(requested_amount, uncapped))

        # Capped regime: cash >= amount + cap
        capped = available_cash - cap
        return max(0.0, min(requested_amount, capped))

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
