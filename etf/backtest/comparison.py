from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional

import pandas as pd

from ..analytics.metrics import compute_kpis
from ..backtest.engine import BacktestEngine
from ..config import BacktestConfig
from ..data.indicators import compute_indicators
from ..data.loader import load_etf_data
from ..models import BacktestResult, KPIReport, Trade
from ..strategies.base import Strategy


class BacktestComparison:
    def __init__(self, cfg: BacktestConfig, strategies: Dict[str, Strategy], benchmark: Optional[str] = None, logger: Optional[logging.Logger] = None):
        self.cfg = cfg
        self.strategies = strategies
        self.benchmark = benchmark
        self.logger = logger or logging.getLogger(__name__)

    def run(self) -> List[BacktestResult]:
        raw_df, vix_series = load_etf_data(self.cfg, self.logger)
        market_df = compute_indicators(raw_df, vix_series, self.cfg)
        results: List[BacktestResult] = []

        for name, strategy in self.strategies.items():
            self.logger.info("Running strategy: %s", name)
            engine = BacktestEngine(self.cfg, strategy, self.logger)
            equity, trades = engine.run_with_data(market_df)
            kpis = compute_kpis(equity, trades, engine.portfolio.state, self.cfg, strategy_name=name)
            results.append(BacktestResult(strategy_name=name, equity=equity, trades=trades, kpis=kpis))

        return results

    @staticmethod
    def build_summary(results: Iterable[BacktestResult]) -> pd.DataFrame:
        rows = []
        for item in results:
            rows.append({
                "strategy": item.strategy_name,
                "cagr": item.kpis.cagr,
                "twrr": item.kpis.twrr,
                "xirr": item.kpis.xirr,
                "sharpe": item.kpis.sharpe_ratio,
                "sortino": item.kpis.sortino_ratio,
                "max_drawdown": item.kpis.max_drawdown,
                "volatility": item.kpis.volatility,
                "ulcer_index": item.kpis.ulcer_index,
                "final_pv": item.kpis.final_portfolio_value,
                "total_invested": item.kpis.total_invested,
                "absolute_return": item.kpis.absolute_return_eur,
                "cash_util": item.kpis.cash_utilization_rate,
                "time_invested_ratio": item.kpis.time_invested_ratio,
                "trades": item.kpis.number_of_trades,
                "avg_buy_price": item.kpis.avg_buy_price,
                "total_trade_costs_eur": item.kpis.total_trade_costs_eur,
            })
        return pd.DataFrame(rows).set_index("strategy").sort_values("cagr", ascending=False)
