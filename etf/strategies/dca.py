from typing import List

from ..config import BacktestConfig
from ..models import MarketState, Order, State
from .base import Strategy


class DollarCostAveragingStrategy(Strategy):
    def __init__(self, cfg: BacktestConfig):
        self.cfg = cfg
        self.accumulated_cash = 0.0

    def on_day(self, market_state: MarketState, portfolio_state: State) -> List[Order]:
        if not market_state.is_month_start:
            return []

        savings = self.cfg.monthly_contribution
        self.accumulated_cash += savings

        if self.accumulated_cash < self.cfg.min_order_eur:
            return []

        exec_price = self._apply_slippage(market_state.close)
        units = self.accumulated_cash / exec_price
        order = Order(
            date=market_state.date,
            amount_eur=round(self.accumulated_cash, 4),
            price=round(exec_price, 6),
            units=round(units, 6),
            tier="MONTHLY-DCA",
        )
        self.accumulated_cash = 0.0
        return [order]

    def _apply_slippage(self, price: float) -> float:
        return price * (1.0 + self.cfg.slippage)
