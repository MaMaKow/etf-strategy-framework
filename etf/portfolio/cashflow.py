from __future__ import annotations

from ..models import State
from ..config import BacktestConfig


class CashFlowManager:
    def __init__(self, cfg: BacktestConfig):
        self.cfg = cfg

    def apply_monthly_contribution(self, state: State, amount: float) -> float:
        if amount <= 0:
            return 0.0

        state.cash_ocf += amount
        state.total_contributions += amount
        state.total_cashflow += amount
        return amount
