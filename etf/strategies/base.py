from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from ..models import MarketState, Order, State


class Strategy(ABC):
    @abstractmethod
    def on_day(self, market_state: MarketState, portfolio_state: State) -> List[Order]:
        """Evaluate market conditions and return list of orders to execute."""
        pass