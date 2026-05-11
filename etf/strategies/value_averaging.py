import logging
import math
from typing import List

from ..config import BacktestConfig
from ..models import MarketState, Order, State
from .base import Strategy


class ValueAveragingStrategy(Strategy):
    def __init__(self, cfg: BacktestConfig):
        self.cfg = cfg
        self.period_counter = 0
        self.logger = logging.getLogger(__name__)

        if self.cfg.value_averaging_base is None or self.cfg.value_averaging_base <= 0:
            self.logger.warning(
                "Value averaging base not set or invalid (%.2f); defaulting to monthly contribution %.2f",
                self.cfg.value_averaging_base,
                self.cfg.monthly_contribution,
            )
            self.cfg.value_averaging_base = self.cfg.monthly_contribution

    def on_day(self, market_state: MarketState, portfolio_state: State) -> List[Order]:
        if not market_state.is_month_start:
            return []

        self.period_counter += 1
        target_value = self._target_value(self.period_counter)
        invested_value = portfolio_state.units * market_state.close
        available_cash = portfolio_state.cash_ocf
        delta = target_value - invested_value

        amount_to_invest = delta if delta > 0 else 0.0

        if amount_to_invest > 0 and amount_to_invest < self.cfg.min_order_eur:
            self.logger.warning(
                "VA month %d target %.2f requires only %.2f, which is below min order %.2f; skipping until next period",
                self.period_counter,
                target_value,
                amount_to_invest,
                self.cfg.min_order_eur,
            )
            self.logger.debug(
                "VA month %d state: target=%.2f invested=%.2f cash=%.2f delta=%.2f order=%.2f",
                self.period_counter,
                target_value,
                invested_value,
                available_cash,
                delta,
                0.0,
            )
            return []

        order_amount = min(amount_to_invest, available_cash)

        self.logger.debug(
            "VA month %d state: target=%.2f invested=%.2f cash=%.2f delta=%.2f order_amount=%.2f",
            self.period_counter,
            target_value,
            invested_value,
            available_cash,
            delta,
            order_amount,
        )

        if order_amount < self.cfg.min_order_eur:
            return []

        exec_price = self._apply_slippage(market_state.close)
        units = order_amount / exec_price

        return [Order(
            date=market_state.date,
            amount_eur=round(order_amount, 4),
            price=round(exec_price, 6),
            units=round(units, 6),
            tier="MONTHLY-VA",
        )]

    def _target_value(self, period_index: int) -> float:
        if self.cfg.value_averaging_mode == "exponential":
            return self.cfg.value_averaging_base * ((1.0 + self.cfg.value_averaging_growth_rate) ** period_index)
        return self.cfg.value_averaging_base * period_index

    def _apply_slippage(self, price: float) -> float:
        return price * (1.0 + self.cfg.slippage)
