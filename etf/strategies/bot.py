import math
from typing import List, Optional

from ..config import SDAConfig
from ..models import MarketState, Order, State
from .base import Strategy


class SignalBotStrategy(Strategy):
    def __init__(self, cfg: SDAConfig):
        self.cfg = cfg

    def on_day(self, market_state: MarketState, portfolio_state: State) -> List[Order]:
        orders: List[Order] = []

        monthly_orders = []
        if market_state.is_month_start:
            monthly_orders = self._support_monthly_savings(market_state, portfolio_state)
            orders.extend(monthly_orders)

        available_cash = portfolio_state.cash_ocf
        if monthly_orders:
            reserved_amount = sum(order.amount_eur for order in monthly_orders)
            available_cash = max(0.0, available_cash - reserved_amount)

        adjusted_state = State(
            cash_ocf=available_cash,
            units=portfolio_state.units,
            portfolio_value=portfolio_state.portfolio_value,
            cooldowns=dict(portfolio_state.cooldowns),
            total_contributions=portfolio_state.total_contributions,
            total_cashflow=portfolio_state.total_cashflow,
        )

        signal_orders = self._evaluate_signals(market_state, adjusted_state)
        orders.extend(signal_orders)
        return orders

    def _support_monthly_savings(self, market_state: MarketState, state: State) -> List[Order]:
        savings = self.cfg.monthly_savings if self.cfg.monthly_savings is not None else self.cfg.monthly_contribution
        if savings >= self.cfg.min_order_eur and state.cash_ocf >= savings:
            return [self._build_order(market_state, savings, "MONTHLY-ETF")]
        return []

    def _evaluate_signals(self, market_state: MarketState, state: State) -> List[Order]:
        if market_state.vix <= self.cfg.vix_threshold or math.isnan(market_state.vix):
            return []
        if math.isnan(market_state.drawdown) or math.isnan(market_state.rsi):
            return []

        recovering = market_state.recovery_days >= self.cfg.recovery_days
        days_l1l2 = state.cooldowns.get("L1L2", 0)
        days_l3 = state.cooldowns.get("L3", 0)
        days_l4 = state.cooldowns.get("L4", 0)

        order = None
        cooldown_days = None

        if (
            days_l1l2 == 0
            and market_state.drawdown <= self.cfg.l1_drawdown
            and market_state.rsi < self.cfg.l1_rsi
            and market_state.vix > self.cfg.vix_threshold
            and recovering
        ):
            order = self._build_order(
                market_state,
                self._scale_amount(self.cfg.l1_amount, market_state.drawdown),
                "L1_ULTIMATE_DIP",
                drawdown=market_state.drawdown,
                vix=market_state.vix,
            )
            cooldown_days = self.cfg.min_days_l1l2
            order.tier = "L1_ULTIMATE_DIP"
            order.cooldown_days = cooldown_days
            order.amount_eur = float(order.amount_eur)
        elif days_l1l2 == 0 and market_state.rsi < self.cfg.l2_rsi and recovering:
            order = self._build_order(
                market_state,
                self.cfg.l2_amount,
                "L2_RSI_EXTREME",
                drawdown=market_state.drawdown,
                vix=market_state.vix,
            )
            cooldown_days = self.cfg.min_days_l1l2
            order.cooldown_days = cooldown_days
        elif (
            days_l3 == 0
            and market_state.close > market_state.sma200
            and market_state.prev_price <= market_state.prev_sma200
            and market_state.rsi < self.cfg.l3_rsi_max
        ):
            order = self._build_order(
                market_state,
                self.cfg.l3_amount,
                "L3_TREND_CROSS",
                drawdown=market_state.drawdown,
                vix=market_state.vix,
            )
            cooldown_days = self.cfg.min_days_l3
            order.cooldown_days = cooldown_days
        elif (
            days_l4 == 0
            and not math.isnan(market_state.sma20)
            and market_state.sma20 != 0.0
            and (market_state.close - market_state.sma20) / market_state.sma20 <= self.cfg.l4_dip_pct
            and market_state.rsi < self.cfg.l4_rsi
            and recovering
        ):
            order = self._build_order(
                market_state,
                self.cfg.l4_amount,
                "L4_MODERATE_DIP",
                drawdown=market_state.drawdown,
                vix=market_state.vix,
            )
            cooldown_days = self.cfg.min_days_l4
            order.cooldown_days = cooldown_days

        if order is None:
            return []

        if order.amount_eur < self.cfg.min_order_eur:
            return []
        if order.amount_eur > state.cash_ocf:
            return []

        return [order]

    def _build_order(
        self,
        market_state: MarketState,
        amount: float,
        tier: str,
        drawdown: Optional[float] = None,
        vix: Optional[float] = None,
        cooldown_days: Optional[int] = None,
    ) -> Order:
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

    def _scale_amount(self, base_amount: float, drawdown: float) -> float:
        factor = 1.0 + abs(drawdown) * self.cfg.drawdown_scale_factor
        scaled = round(base_amount * factor / 25) * 25
        return max(base_amount, scaled)
