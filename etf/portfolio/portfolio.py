from ..models import Order, State, Trade


class Portfolio:
    def __init__(self, initial_state: State = None):
        self.state = initial_state or State()

    def execute_order(self, order: Order) -> Trade:
        if order.tier.startswith("T"):  # Dip buy
            if order.amount_eur > self.state.cash_ocf:
                raise ValueError("Insufficient cash for order")
            self.state.cash_ocf -= order.amount_eur
            self.state.units += order.units
            # Set cooldown - but cooldown is in state, strategy shouldn't set it
            # For now, assume engine sets cooldown
        elif order.tier == "MONTHLY-ETF":
            self.state.units += order.units
        else:
            raise ValueError(f"Unknown order tier: {order.tier}")

        return Trade(
            date=order.date,
            tier=order.tier,
            amount_eur=order.amount_eur,
            price=order.price,
            units=order.units,
            drawdown=order.drawdown,
            vix=order.vix,
            cash_left=self.state.cash_ocf
        )

    def add_monthly_savings(self, savings: float):
        ocf = self.state.cash_ocf
        target = 5000.0  # From config, but hardcoded for now
        if ocf < 0.30 * target:
            self.state.cash_ocf += savings
            self.state.total_ocf_inflow += savings
        elif ocf < 1.00 * target:
            ocf_part = 0.30 * savings
            self.state.cash_ocf += ocf_part
            self.state.total_ocf_inflow += ocf_part
            # ETF part is in order
        else:
            # All to ETF, but if no order, add to cash?
            pass  # Handled by strategy

    def update_portfolio_value(self, price: float):
        self.state.portfolio_value = self.state.units * price + self.state.cash_ocf

    def decrement_cooldowns(self):
        spent = []
        for lbl in list(self.state.cooldowns):
            self.state.cooldowns[lbl] -= 1
            if self.state.cooldowns[lbl] <= 0:
                spent.append(lbl)
        for lbl in spent:
            del self.state.cooldowns[lbl]

    def set_cooldown(self, tier: str, days: int):
        self.state.cooldowns[tier] = days