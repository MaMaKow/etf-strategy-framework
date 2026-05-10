import logging
from itertools import product as iterproduct
from typing import List, Optional

import pandas as pd

from ..analytics.metrics import compute_kpis
from ..backtest.engine import BacktestEngine
from ..config import SDAConfig
from ..models import SweepResult
from ..strategies.sda import SDAStrategy


def parameter_sweep(
    base_cfg: SDAConfig,
    logger: logging.Logger,
    ocf_targets: Optional[List[float]] = None,
    monthly_savings_list: Optional[List[float]] = None,
    vix_thresholds: Optional[List[float]] = None,
) -> pd.DataFrame:
    ocf_targets = ocf_targets or [3000.0, 5000.0, 8000.0]
    monthly_savings_list = monthly_savings_list or [500.0, 1000.0, 2000.0]
    vix_thresholds = vix_thresholds or [12.0, 15.0, 20.0]

    combos = list(iterproduct(ocf_targets, monthly_savings_list, vix_thresholds))
    logger.info("Parameter sweep: %d combinations", len(combos))

    results = []
    for i, (ocf_t, savings, vix_t) in enumerate(combos):
        cfg_i = SDAConfig(
            etf_ticker=base_cfg.etf_ticker,
            vix_ticker=base_cfg.vix_ticker,
            start_date=base_cfg.start_date,
            end_date=base_cfg.end_date,
            monthly_savings=savings,
            ocf_target=ocf_t,
            vix_threshold=vix_t,
            min_order_eur=base_cfg.min_order_eur,
            slippage=base_cfg.slippage,
            log_level="WARNING",
        )
        sweep_logger = logging.getLogger(f"SDA.sweep.{i}")
        sweep_logger.setLevel(logging.WARNING)
        if not sweep_logger.handlers:
            sweep_logger.addHandler(logging.NullHandler())

        strategy = SDAStrategy(cfg_i)
        engine = BacktestEngine(cfg_i, strategy, sweep_logger)
        equity, trades = engine.run()
        kpis = compute_kpis(equity, trades, engine.portfolio.state, cfg_i)

        results.append(SweepResult(
            ocf_target=ocf_t,
            monthly_savings=savings,
            vix_threshold=vix_t,
            cagr=kpis.cagr,
            max_dd=kpis.max_drawdown,
            sharpe=kpis.sharpe_ratio,
            final_pv=kpis.final_portfolio_value,
            dip_buys=kpis.dip_buys_count,
            cash_util=kpis.cash_utilization_rate,
        ))

        logger.info("Sweep %d/%d  OCF=%.0f  Sav=%.0f  VIX=%.0f  → Sharpe %.3f",
                    i + 1, len(combos), ocf_t, savings, vix_t, kpis.sharpe_ratio)

    result_df = pd.DataFrame([vars(r) for r in results]).sort_values("sharpe", ascending=False).reset_index(drop=True)
    return result_df