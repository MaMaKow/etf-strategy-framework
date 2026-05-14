import argparse
import csv
import logging
import sys
from typing import Dict, List
from datetime import date

from ..analytics.metrics import compute_kpis
from ..analytics.reports import plot_comparison_equity, plot_equity_curve, print_kpi_summary
from ..backtest.comparison import BacktestComparison
from ..backtest.engine import BacktestEngine
from ..backtest.sweep import parameter_sweep
from ..config import BacktestConfig, SDAConfig
from ..models import Trade
from ..strategies.dca import DollarCostAveragingStrategy
from ..strategies.sda import SDAStrategy
from ..strategies.value_averaging import ValueAveragingStrategy
from ..strategies.bot import SignalBotStrategy
from ..sda_bot import SDABot, init_bot, run_daily


STRATEGY_REGISTRY = {
    "sda": SDAStrategy,
    "dca": DollarCostAveragingStrategy,
    "value_averaging": ValueAveragingStrategy,
    "bot": SignalBotStrategy,
}


def setup_logging(level: str) -> logging.Logger:
    logger = logging.getLogger("ETF")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(handler)
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


def build_config(args: argparse.Namespace) -> BacktestConfig:
    # Handle MAX dates
    start_date = args.start
    end_date = args.end

    if start_date.upper() == "MAX":
        start_date = "1900-01-01"  # Very early date to get all available data
    if end_date.upper() == "MAX":
        end_date = date.today().strftime("%Y-%m-%d")   # Today date to get all available data

    cfg = SDAConfig(
        etf_ticker=args.ticker,
        vix_ticker=args.vix_ticker,
        start_date=start_date,
        end_date=end_date,
        monthly_contribution=args.monthly,
        monthly_savings=args.monthly_savings,
        ocf_target=args.ocf_target,
        min_order_eur=args.min_order,
        slippage=args.slippage,
        log_level=args.log_level,
        export_trades_csv=args.export_trades_csv or "",
        value_averaging_mode=args.va_mode,
        value_averaging_base=args.va_base,
        value_averaging_growth_rate=args.va_rate,
        value_averaging_allow_negative=args.va_allow_negative,
    )
    return cfg


def make_strategy(name: str, cfg: BacktestConfig):
    name = name.strip().lower()
    if name not in STRATEGY_REGISTRY:
        raise ValueError(f"Unknown strategy: {name}")
    return STRATEGY_REGISTRY[name](cfg)


def run_single_strategy(cfg: BacktestConfig, strategy_name: str, logger: logging.Logger) -> None:
    strategy = make_strategy(strategy_name, cfg)
    engine = BacktestEngine(cfg, strategy, logger)
    equity, trades = engine.run()
    kpis = compute_kpis(equity, trades, engine.portfolio.state, cfg, strategy_name=strategy_name)
    print_kpi_summary(kpis, cfg)
    if cfg.export_trades_csv:
        export_trades_csv(trades, cfg.export_trades_csv)
    plot_equity_curve(equity, trades, cfg, strategy_name)


def run_comparison(cfg: BacktestConfig, strategy_names: List[str], logger: logging.Logger) -> None:
    strategies = {name: make_strategy(name, cfg) for name in strategy_names}
    comparison = BacktestComparison(cfg, strategies, logger=logger)
    results = comparison.run()
    summary_df = BacktestComparison.build_summary(results)
    print(summary_df.to_string(float_format="{:.4f}".format))
    plot_comparison_equity([{"strategy": r.strategy_name, "equity": r.equity} for r in results], cfg)


def main() -> None:
    parser = argparse.ArgumentParser(description="ETF strategy comparison CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--ticker", default="EUNL.DE")
    common.add_argument("--vix-ticker", default="^VIX")
    common.add_argument("--start", default="2014-01-01", help="Start date (YYYY-MM-DD) or 'MAX' for earliest available data")
    common.add_argument("--end", default="2024-12-31", help="End date (YYYY-MM-DD) or 'MAX' for latest available data")
    common.add_argument("--monthly", type=float, default=150.0,
                        help="Total monthly cash inflow into the strategy")
    common.add_argument("--monthly-savings", type=float, default=None,
                        help="Amount of total monthly cash used for the regular ETF savings order (must not exceed --monthly)")
    common.add_argument("--min-order", type=float, default=100.0)
    common.add_argument("--slippage", type=float, default=0.0005)
    common.add_argument("--log-level", default="INFO")
    common.add_argument("--export-trades-csv", default="")
    common.add_argument("--ocf-target", type=float, default=100.0)
    common.add_argument("--va-mode", choices=["linear", "exponential"], default="linear")
    common.add_argument("--va-base", type=float, default=1000.0)
    common.add_argument("--va-rate", type=float, default=0.0)
    common.add_argument("--va-allow-negative", action="store_true")

    parser_run = subparsers.add_parser("run", parents=[common], help="Run one strategy")
    parser_run.add_argument("--strategy", choices=list(STRATEGY_REGISTRY), required=True)

    parser_compare = subparsers.add_parser("compare", parents=[common], help="Compare multiple strategies")
    parser_compare.add_argument("--strategies", required=True, help="Comma-separated strategy keys")

    parser_sweep = subparsers.add_parser("sweep", parents=[common], help="Sweep strategy parameters")
    parser_sweep.add_argument("--strategy", choices=list(STRATEGY_REGISTRY), required=False,
                              help="Single strategy to sweep")
    parser_sweep.add_argument("--strategies", help="Comma-separated strategies to sweep (default: all)")

    # SDA Bot commands
    bot_common = argparse.ArgumentParser(add_help=False)
    bot_common.add_argument("--log-level", default="INFO")

    parser_bot_init = subparsers.add_parser("bot-init", parents=[bot_common], help="Initialize SDA bot database")
    parser_bot_run = subparsers.add_parser("bot-run", parents=[bot_common], help="Run SDA bot for a specific ETF")
    parser_bot_run.add_argument("--ticker", default="EUNL.DE", help="ETF ticker to evaluate")

    args = parser.parse_args()
    logger = setup_logging(args.log_level)
    cfg = build_config(args) if hasattr(args, 'start') else None

    if args.command == "run":
        run_single_strategy(cfg, args.strategy, logger)
    elif args.command == "compare":
        names = [name.strip() for name in args.strategies.split(",") if name.strip()]
        run_comparison(cfg, names, logger)
    elif args.command == "sweep":
        if args.strategies:
            strategy_names = [name.strip() for name in args.strategies.split(",") if name.strip()]
        elif args.strategy:
            strategy_names = [args.strategy]
        else:
            strategy_names = list(STRATEGY_REGISTRY.keys())

        strategy_factories = {
            name: STRATEGY_REGISTRY[name] for name in strategy_names
        }
        sweep_df = parameter_sweep(cfg, logger, strategy_factories=strategy_factories)
        output_path = f"{'_'.join(strategy_names)}_sweep_results.csv"
        sweep_df.to_csv(output_path, index=False)
        print(f"\n  [Sweep results saved → {output_path}]")
    elif args.command == "bot-init":
        init_bot()
    elif args.command == "bot-run":
        run_daily(args.ticker)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
