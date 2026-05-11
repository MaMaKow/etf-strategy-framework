from __future__ import annotations

from ..models import Order, State, Trade


class Portfolio:
    def __init__(self, initial_state: State = None):
        self.state = initial_state or State()

    def execute_order(self, order: Order) -> Trade:
        if order.amount_eur > self.state.cash_ocf:
            raise ValueError("Insufficient cash for order")

        self.state.cash_ocf -= order.amount_eur
        self.state.units += order.units

        return Trade(
            date=order.date,
            tier=order.tier,
            amount_eur=order.amount_eur,
            price=order.price,
            units=order.units,
            drawdown=order.drawdown,
            vix=order.vix,
            cash_left=self.state.cash_ocf,
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
