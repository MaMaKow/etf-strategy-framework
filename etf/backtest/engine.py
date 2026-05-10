import logging
from typing import List, Tuple

import pandas as pd

from ..analytics.metrics import compute_kpis
from ..config import SDAConfig
from ..data.indicators import compute_indicators
from ..data.loader import load_etf_data
from ..models import MarketState, PortfolioSnapshot, State, Trade
from ..portfolio.cashflow import CashFlowManager
from ..portfolio.portfolio import Portfolio
from ..strategies.base import Strategy


class BacktestEngine:
    def __init__(self, cfg: SDAConfig, strategy: Strategy, logger: logging.Logger):
        self.cfg = cfg
        self.strategy = strategy
        self.logger = logger
        self.portfolio = Portfolio()
        self.cash_manager = CashFlowManager(cfg)

    def run(self) -> Tuple[pd.DataFrame, List[Trade]]:
        # Load data
        df_raw, vix_series = load_etf_data(self.cfg, self.logger)
        df = compute_indicators(df_raw, vix_series, self.cfg)

        trades = []
        equity_rows = []

        n = len(df)
        self.logger.info("Starting simulation: %d trading days", n)

        for i, (idx, row) in enumerate(df.iterrows()):
            price = float(row["close"])

            # Decrement cooldowns
            self.portfolio.decrement_cooldowns()

            # Monthly savings
            if bool(row["is_month_start"]):
                self.cash_manager.apply_monthly_savings(self.portfolio.state, self.cfg.monthly_savings)

            # Get market state
            market_state = MarketState(
                date=idx.date(),
                close=price,
                drawdown=float(row["drawdown"]),
                sma200=float(row["sma200"]),
                vix=float(row["vix"]),
                is_month_start=bool(row["is_month_start"])
            )

            # Strategy decisions
            orders = self.strategy.on_day(market_state, self.portfolio.state)

            # Execute orders
            for order in orders:
                if order.tier.startswith("T"):  # Dip buy
                    if order.amount_eur <= self.portfolio.state.cash_ocf:
                        trade = self.portfolio.execute_order(order)
                        trades.append(trade)
                        # Set cooldown
                        cd = self.strategy._cooldown_days(order.drawdown)  # Hack, should be in strategy
                        self.portfolio.set_cooldown(order.tier, cd)
                        self.logger.info(
                            "BUY  | %s | %-3s | %9.2f EUR | Price %8.4f | OCF left %9.2f | CD %d days",
                            order.date, order.tier, order.amount_eur, order.price, self.portfolio.state.cash_ocf, cd,
                        )
                elif order.tier == "MONTHLY-ETF":
                    trade = self.portfolio.execute_order(order)
                    trades.append(trade)
                    self.logger.debug("%s | Monthly ETF %.2f EUR @ %.4f",
                                     order.date, order.amount_eur, order.price)

            # Update portfolio value
            self.portfolio.update_portfolio_value(price)

            equity_rows.append({
                "date": idx,
                "close": price,
                "portfolio_value": self.portfolio.state.portfolio_value,
                "units": self.portfolio.state.units,
                "cash_ocf": self.portfolio.state.cash_ocf,
                "drawdown": float(row["drawdown"]),
                "vix": float(row["vix"]),
                "sma200": float(row["sma200"])
            })

            if (i + 1) % 250 == 0 or (i + 1) == n:
                self.logger.info("Progress: %d / %d  |  PV: %.2f EUR  |  Units: %.4f  |  OCF: %.2f",
                                i + 1, n, self.portfolio.state.portfolio_value, self.portfolio.state.units, self.portfolio.state.cash_ocf)

        equity = pd.DataFrame(equity_rows).set_index("date")
        return equity, trades