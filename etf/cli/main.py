import csv
import logging
import sys
from pathlib import Path
from typing import List

from ..models import Trade
from ..analytics.metrics import compute_kpis
from ..analytics.reports import plot_equity_curve, print_kpi_summary
from ..backtest.engine import BacktestEngine
from ..backtest.sweep import parameter_sweep
from ..config import SDAConfig
from ..strategies.sda import SDAStrategy


def setup_logging(level: str) -> logging.Logger:
    logger = logging.getLogger("SDA")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                         datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(h)
    return logger


def export_trades_csv(trades: List[Trade], path: str) -> None:
    if not trades:
        return
    keys = ["date", "tier", "amount_eur", "price", "units", "drawdown", "vix", "cash_left"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows([vars(t) for t in trades])
    print(f"  [Trade log saved → {path}]")


def main(run_sweep: bool = False) -> None:
    cfg = SDAConfig(
        etf_ticker="EUNL.DE",
        start_date="2014-01-01",
        end_date="2024-12-31",
        monthly_savings=1000.0,
        ocf_target=5000.0,
        vix_threshold=15.0,
        min_order_eur=500.0,
        slippage=0.0005,
        log_level="INFO",
        export_trades_csv="sda_trades.csv",
    )

    logger = setup_logging(cfg.log_level)

    logger.info("═══════════════════════════════════════════════")
    logger.info("   Systematic Drawdown Accumulator  v2.0")
    logger.info("   ETF   : %s", cfg.etf_ticker)
    logger.info("   Period: %s → %s", cfg.start_date, cfg.end_date)
    logger.info("   OCF target  : %.0f EUR", cfg.ocf_target)
    logger.info("   Monthly sav : %.0f EUR", cfg.monthly_savings)
    logger.info("   VIX filter  : > %.1f", cfg.vix_threshold)
    logger.info("   Min order   : %.0f EUR", cfg.min_order_eur)
    logger.info("   Slippage    : %.2f %%", cfg.slippage * 100)
    logger.info("═══════════════════════════════════════════════")

    strategy = SDAStrategy(cfg)
    engine = BacktestEngine(cfg, strategy, logger)
    equity, trades = engine.run()

    kpis = compute_kpis(equity, trades, engine.portfolio.state, cfg)
    print_kpi_summary(kpis, cfg)

    if cfg.export_trades_csv:
        export_trades_csv(trades, cfg.export_trades_csv)

    plot_equity_curve(equity, trades, cfg)

    if run_sweep:
        logger.info("Starting parameter sweep …")
        sweep_df = parameter_sweep(
            cfg, logger,
            ocf_targets=[3000.0, 5000.0, 8000.0],
            monthly_savings_list=[500.0, 1000.0, 2000.0],
            vix_thresholds=[12.0, 15.0, 20.0],
        )
        sweep_path = "sda_sweep_results.csv"
        sweep_df.to_csv(sweep_path, index=False)
        print(f"\n  Top 5 sweep results (by Sharpe):")
        print(sweep_df.head(5).to_string(index=False))
        print(f"\n  [Full sweep saved → {sweep_path}]")


if __name__ == "__main__":
    _sweep = "--sweep" in sys.argv
    main(run_sweep=_sweep)