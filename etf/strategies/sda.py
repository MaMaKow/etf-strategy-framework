import math
from typing import List

from ..config import SDAConfig
from ..models import MarketState, Order, State
from .base import Strategy


class SDAStrategy(Strategy):
    def __init__(self, cfg: SDAConfig):
        self.cfg = cfg

    def on_day(self, market_state: MarketState, portfolio_state: State) -> List[Order]:
        orders: List[Order] = []

        monthly_orders = []
        if market_state.is_month_start:
            monthly_orders = self._support_ocf_and_monthly_savings(market_state, portfolio_state)
            orders.extend(monthly_orders)

        available_cash = portfolio_state.cash_ocf
        if monthly_orders:
            reserved_amount = sum(order.amount_eur for order in monthly_orders)
            available_cash = max(0.0, portfolio_state.cash_ocf - reserved_amount)

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

    def _support_ocf_and_monthly_savings(self, market_state: MarketState, state: State) -> List[Order]:
        savings = self.cfg.monthly_savings
        if state.cash_ocf < self.cfg.ocf_low_pct * self.cfg.ocf_target:
            return []
        elif state.cash_ocf < self.cfg.ocf_mid_pct * self.cfg.ocf_target:
            etf_part = 0.70 * savings
            if etf_part >= self.cfg.min_order_eur:
                return [self._build_order(market_state, etf_part, "MONTHLY-ETF")]
            return []
        else:
            if savings >= self.cfg.min_order_eur:
                return [self._build_order(market_state, savings, "MONTHLY-ETF")]
            return []

    def _evaluate_dip_buys(self, market_state: MarketState, state: State) -> List[Order]:
        if market_state.vix <= self.cfg.vix_threshold or math.isnan(market_state.vix):
            return []
        if math.isnan(market_state.drawdown):
            return []

        for threshold, ocf_frac, label in reversed(self.cfg.dip_tiers):
            if market_state.drawdown > threshold:
                continue
            if label in state.cooldowns:
                continue
            if label == "T1" and self.cfg.t1_requires_above_sma200:
                if market_state.close <= market_state.sma200:
                    continue

            amount_eur = ocf_frac * state.cash_ocf
            if amount_eur < self.cfg.min_order_eur:
                continue

            return [self._build_order(market_state, amount_eur, label, drawdown=market_state.drawdown, vix=market_state.vix, cooldown_days=self._cooldown_days(market_state.drawdown))]

        return []

    def _build_order(self, market_state: MarketState, amount: float, tier: str, drawdown: float = None, vix: float = None, cooldown_days: int = None) -> Order:
        exec_price = self._apply_slippage(market_state.close)
        units = amount / exec_price
        return Order(
            date=market_state.date,
            amount_eur=round(amount, 4),
            price=round(exec_price, 6),
            units=round(units, 6),
            tier=tier,
            drawdown=round(drawdown, 6) if drawdown is not None else None,
            vix=round(vix, 2) if vix is not None else None,
            cooldown_days=cooldown_days,
        )

    def _apply_slippage(self, price: float) -> float:
        return price * (1.0 + self.cfg.slippage)

    def _cooldown_days(self, drawdown: float) -> int:
        if math.isnan(drawdown):
            return self.cfg.cooldown_min
        raw = int(20 * math.exp(3 * drawdown))
        return max(self.cfg.cooldown_min, raw)
