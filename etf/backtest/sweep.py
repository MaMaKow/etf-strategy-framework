from __future__ import annotations

import logging
from copy import deepcopy
from itertools import product as iterproduct
from typing import Callable, Dict, List, Optional

import pandas as pd

from ..analytics.metrics import compute_kpis
from ..backtest.engine import BacktestEngine
from ..config import BacktestConfig
from ..models import SweepResult
from ..strategies.base import Strategy
from ..strategies.sda import SDAStrategy


StrategyFactory = Callable[[BacktestConfig], Strategy]


def parameter_sweep(
    base_cfg: BacktestConfig,
    logger: logging.Logger,
    strategy_factories: Optional[Dict[str, StrategyFactory]] = None,
    param_grid: Optional[Dict[str, List[float]]] = None,
) -> pd.DataFrame:
    strategy_factories = strategy_factories or {"sda": SDAStrategy}
    param_grid = param_grid or {
    "ocf_target": [150, 300, 500,750,1000,1500,2000],
    "monthly_contribution": [150,200,250,300,400,500],
        "min_order_eur": [100, 250, 500, 1000],
    "vix_threshold": [10.0],
}

    keys = list(param_grid.keys())
    combos = list(iterproduct(*(param_grid[key] for key in keys)))
    logger.info("Parameter sweep: %d combinations x %d strategies", len(combos), len(strategy_factories))

    results = []
    for strategy_name, factory in strategy_factories.items():
        for i, combo in enumerate(combos):
            cfg_i = deepcopy(base_cfg)
            for key, value in zip(keys, combo):
                if key == "monthly_contribution" and hasattr(cfg_i, "monthly_savings"):
                    if cfg_i.monthly_savings == cfg_i.monthly_contribution:
                        cfg_i.monthly_savings = value
                    cfg_i.monthly_contribution = value
                elif key == "monthly_savings" and hasattr(cfg_i, "monthly_contribution"):
                    cfg_i.monthly_savings = value
                elif hasattr(cfg_i, key):
                    setattr(cfg_i, key, value)
                else:
                    raise AttributeError(f"Configuration has no field '{key}'")

            sweep_logger = logging.getLogger(f"BacktestSweep.{strategy_name}.{i}")
            sweep_logger.setLevel(logging.WARNING)
            if not sweep_logger.handlers:
                sweep_logger.addHandler(logging.NullHandler())

            strategy = factory(cfg_i)
            engine = BacktestEngine(cfg_i, strategy, sweep_logger)
            equity, trades = engine.run()
            kpis = compute_kpis(equity, trades, engine.portfolio.state, cfg_i, strategy_name=strategy_name)

            results.append(SweepResult(
                strategy=strategy_name,
                parameter_set={key: value for key, value in zip(keys, combo)},
                cagr=kpis.cagr,
                twrr=kpis.twrr,
                xirr=kpis.xirr,
                sharpe=kpis.sharpe_ratio,
                sortino=kpis.sortino_ratio,
                max_dd=kpis.max_drawdown,
                final_pv=kpis.final_portfolio_value,
                total_invested=kpis.total_invested,
                cash_util=kpis.cash_utilization_rate,
                trades=kpis.number_of_trades,
            ))

            logger.info("Sweep [%s] %d/%d  %s → Sharpe %.3f", strategy_name, i + 1, len(combos), cfg_i, kpis.sharpe_ratio)

    result_df = pd.DataFrame([{
        "strategy": r.strategy,
        **r.parameter_set,
        "cagr": r.cagr,
        "twrr": r.twrr,
        "xirr": r.xirr,
        "sharpe": r.sharpe,
        "sortino": r.sortino,
        "max_dd": r.max_dd,
        "final_pv": r.final_pv,
        "total_invested": r.total_invested,
        "cash_util": r.cash_util,
        "trades": r.trades,
    } for r in results])
    return result_df.sort_values(["strategy", "sharpe"], ascending=[True, False]).reset_index(drop=True)
