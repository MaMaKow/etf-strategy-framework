from __future__ import annotations

from ..config import BacktestConfig
from ..models import Order, State, Trade


class Portfolio:
    def __init__(self, cfg: BacktestConfig, initial_state: State = None):
        self.cfg = cfg
        self.state = initial_state or State()

    def _order_fee(self, order: Order) -> float:
        if order.amount_eur <= 0:
            return 0.0
        if order.tier.startswith("MONTHLY-"):
            return 0.0
        fee = self.cfg.broker_base_fee_eur + (self.cfg.broker_variable_fee_rate * order.amount_eur)
        return float(min(fee, self.cfg.broker_fee_cap_eur))

    def execute_order(self, order: Order) -> Trade:
        fee_eur = self._order_fee(order)
        total_cash_needed = order.amount_eur + fee_eur
        if total_cash_needed > self.state.cash_ocf:
            raise ValueError("Insufficient cash for order")

        net_invested_eur = max(0.0, order.amount_eur - fee_eur)
        units_bought = net_invested_eur / order.price if order.price > 0 else 0.0

        self.state.cash_ocf -= total_cash_needed
        self.state.units += units_bought

        return Trade(
            date=order.date,
            tier=order.tier,
            amount_eur=order.amount_eur,
            price=order.price,
            units=units_bought,
            drawdown=order.drawdown,
            vix=order.vix,
            cash_left=self.state.cash_ocf,
            fee_eur=fee_eur,
        )

    def add_cash(self, amount: float) -> None:
        self.state.cash_ocf += amount
        self.state.total_contributions += amount
        self.state.total_cashflow += amount

    def update_portfolio_value(self, price: float) -> None:
        self.state.portfolio_value = self.state.units * price + self.state.cash_ocf

    def decrement_cooldowns(self) -> None:
        expired = [label for label, days in self.state.cooldowns.items() if days <= 1]
        for label in list(self.state.cooldowns):
            self.state.cooldowns[label] -= 1
            if self.state.cooldowns[label] <= 0:
                del self.state.cooldowns[label]

    def set_cooldown(self, tier: str, days: int) -> None:
        self.state.cooldowns[tier] = days
