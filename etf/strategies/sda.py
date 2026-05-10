import math
from typing import List

from ..config import SDAConfig
from ..models import MarketState, Order, State


class SDAStrategy:
    def __init__(self, cfg: SDAConfig):
        self.cfg = cfg

    def on_day(self, market_state: MarketState, portfolio_state: State) -> List[Order]:
        orders = []

        # Monthly savings
        if market_state.is_month_start:
            orders.extend(self._apply_monthly_savings(market_state, portfolio_state))

        # Dip buys
        orders.extend(self._evaluate_dip_buys(market_state, portfolio_state))

        return orders

    def _apply_monthly_savings(self, market_state: MarketState, state: State) -> List[Order]:
        savings = self.cfg.monthly_savings
        ocf = state.cash_ocf
        target = self.cfg.ocf_target

        if ocf < self.cfg.ocf_low_pct * target:
            # 100 % → OCF - no order
            return []
        elif ocf < self.cfg.ocf_mid_pct * target:
            # 70 % ETF, 30 % OCF
            etf_part = 0.70 * savings
            if etf_part >= self.cfg.min_order_eur:
                exec_price = self._apply_slippage(market_state.close)
                units_bought = etf_part / exec_price
                return [Order(
                    date=market_state.date,
                    amount_eur=round(etf_part, 4),
                    price=round(exec_price, 6),
                    units=round(units_bought, 6),
                    tier="MONTHLY-ETF",
                    drawdown=None,
                    vix=None
                )]
            else:
                return []
        else:
            # 100 % ETF
            if savings >= self.cfg.min_order_eur:
                exec_price = self._apply_slippage(market_state.close)
                units_bought = savings / exec_price
                return [Order(
                    date=market_state.date,
                    amount_eur=round(savings, 4),
                    price=round(exec_price, 6),
                    units=round(units_bought, 6),
                    tier="MONTHLY-ETF",
                    drawdown=None,
                    vix=None
                )]
            else:
                return []

    def _evaluate_dip_buys(self, market_state: MarketState, state: State) -> List[Order]:
        # VIX filter
        if market_state.vix <= self.cfg.vix_threshold:
            return []
        if math.isnan(market_state.vix):
            return []

        # Evaluate tiers
        for threshold, ocf_frac, label in reversed(self.cfg.dip_tiers):
            if market_state.drawdown > threshold:
                continue
            if label in state.cooldowns:  # Engine should check
                continue
            if label == "T1" and self.cfg.t1_requires_above_sma200:
                if market_state.close <= market_state.sma200:
                    continue

            amount_eur = ocf_frac * state.cash_ocf
            if amount_eur < self.cfg.min_order_eur:
                continue

            exec_price = self._apply_slippage(market_state.close)
            units_bought = amount_eur / exec_price

            return [Order(
                date=market_state.date,
                amount_eur=round(amount_eur, 4),
                price=round(exec_price, 6),
                units=round(units_bought, 6),
                tier=label,
                drawdown=round(market_state.drawdown, 6),
                vix=round(market_state.vix, 2)
            )]
        return []

    def _apply_slippage(self, price: float) -> float:
        return price * (1.0 + self.cfg.slippage)

    def _cooldown_days(self, drawdown: float) -> int:
        if math.isnan(drawdown):
            return 5  # default
        raw = int(20 * math.exp(3 * drawdown))
        return max(self.cfg.cooldown_min, raw)