import logging
from typing import List, Optional, Tuple

import pandas as pd

from ..analytics.metrics import compute_kpis
from ..config import BacktestConfig
from ..data.indicators import compute_indicators
from ..data.loader import load_etf_data
from ..models import MarketState, Order, State, Trade
from ..portfolio.cashflow import CashFlowManager
from ..portfolio.portfolio import Portfolio
from ..strategies.base import Strategy


class BacktestEngine:
    def __init__(self, cfg: BacktestConfig, strategy: Strategy, logger: logging.Logger):
        self.cfg = cfg
        self.strategy = strategy
        self.logger = logger
        self.portfolio = Portfolio(cfg, State(cash_ocf=cfg.initial_cash))
        self.cash_manager = CashFlowManager(cfg)

    def run(self, df: Optional[pd.DataFrame] = None) -> Tuple[pd.DataFrame, List[Trade]]:
        if df is None:
            raw_df, vix_series = load_etf_data(self.cfg, self.logger)
            df = compute_indicators(raw_df, vix_series, self.cfg)
        else:
            df = df.copy()

        trades: List[Trade] = []
        equity_rows = []
        n = len(df)
        self.logger.info("Starting simulation: %d trading days", n)

        for i, (idx, row) in enumerate(df.iterrows()):
            price = float(row["close"])
            self.portfolio.decrement_cooldowns()

            cashflow_amount = 0.0
            if bool(row["is_month_start"]):
                cashflow_amount = self.cash_manager.apply_monthly_contribution(self.portfolio.state, self.cfg.monthly_contribution)

            market_state = MarketState(
                date=idx.date(),
                close=price,
                drawdown=float(row["drawdown"]),
                sma200=float(row["sma200"]),
                sma20=float(row["sma20"]),
                rsi=float(row["rsi"]),
                prev_price=float(row["prev_price"]),
                prev_sma200=float(row["prev_sma200"]),
                recovery_days=int(row["recovery_days"]),
                vix=float(row["vix"]),
                is_month_start=bool(row["is_month_start"]),
            )

            orders = self.strategy.on_day(market_state, self.portfolio.state)
            for order in orders:
                trade = self.portfolio.execute_order(order)
                trades.append(trade)
                if order.cooldown_days is not None:
                    self.portfolio.set_cooldown(order.tier, order.cooldown_days)

            self.portfolio.update_portfolio_value(price)
            equity_rows.append({
                "date": idx,
                "close": price,
                "portfolio_value": self.portfolio.state.portfolio_value,
                "units": self.portfolio.state.units,
                "cash_ocf": self.portfolio.state.cash_ocf,
                "drawdown": float(row["drawdown"]),
                "vix": float(row["vix"]),
                "is_month_start": bool(row["is_month_start"]),
                "cashflow": float(cashflow_amount),
            })

            if (i + 1) % 250 == 0 or (i + 1) == n:
                self.logger.info("Progress: %d / %d  |  PV: %.2f EUR  |  Units: %.4f  |  Cash: %.2f",
                                 i + 1, n, self.portfolio.state.portfolio_value, self.portfolio.state.units, self.portfolio.state.cash_ocf)

        equity = pd.DataFrame(equity_rows).set_index("date")
        return equity, trades

    def run_with_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[Trade]]:
        return self.run(df=df)

    def run_and_score(self, df: Optional[pd.DataFrame] = None) -> Tuple[pd.DataFrame, List[Trade], object]:
        equity, trades = self.run(df=df)
        kpis = compute_kpis(equity, trades, self.portfolio.state, self.cfg)
        return equity, trades, kpis
