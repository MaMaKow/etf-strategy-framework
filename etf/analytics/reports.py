import matplotlib.pyplot as plt
import pandas as pd
from typing import List

from ..config import BacktestConfig
from ..models import KPIReport, Trade


def print_kpi_summary(kpis: KPIReport, cfg: BacktestConfig) -> None:
    sep = "─" * 70
    print(f"\n{sep}")
    print(f"  Strategy: {kpis.strategy_name}")
    print(f"  ETF: {cfg.etf_ticker}   |   {cfg.start_date} → {cfg.end_date}")
    print(sep)
    print(f"  {'CAGR':<30} {kpis.cagr:>10.2%}")
    print(f"  {'TWRR':<30} {kpis.twrr:>10.2%}")
    print(f"  {'XIRR':<30} {kpis.xirr:>10.2%}")
    print(f"  {'Sharpe Ratio':<30} {kpis.sharpe_ratio:>10.3f}")
    print(f"  {'Sortino Ratio':<30} {kpis.sortino_ratio:>10.3f}")
    print(f"  {'Max Drawdown':<30} {kpis.max_drawdown:>10.2%}")
    print(f"  {'Volatility':<30} {kpis.volatility:>10.2%}")
    print(f"  {'Ulcer Index':<30} {kpis.ulcer_index:>10.2f}")
    print(sep)
    print(f"  {'Final Portfolio Value':<30} {kpis.final_portfolio_value:>10,.2f} EUR")
    print(f"  {'Total Invested':<30} {kpis.total_invested:>10,.2f} EUR")
    print(f"  {'Absolute Return':<30} {kpis.absolute_return_eur:>10,.2f} EUR")
    print(f"  {'Cash Utilization':<30} {kpis.cash_utilization_rate:>10.2%}")
    print(f"  {'Time Invested Ratio':<30} {kpis.time_invested_ratio:>10.2%}")
    print(f"  {'Number of Trades':<30} {kpis.number_of_trades:>10d}")
    print(f"  {'Avg Buy Price':<30} {kpis.avg_buy_price:>10.4f}")
    print(sep)


def plot_equity_curve(equity: pd.DataFrame, trades: List[Trade], cfg: BacktestConfig, strategy_name: str) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    fig.suptitle(f"{strategy_name} – {cfg.etf_ticker} ({cfg.start_date} → {cfg.end_date})", fontsize=12, fontweight="bold")

    ax1 = axes[0]
    ax1.plot(equity.index, equity["portfolio_value"], label="Portfolio Value", color="#1f77b4")
    ax1.fill_between(equity.index, equity["portfolio_value"], alpha=0.1, color="#1f77b4")
    ax1.set_ylabel("Portfolio Value (EUR)")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(alpha=0.3)

    ax2 = axes[1]
    ax2.plot(equity.index, equity["cash_ocf"], label="Cash Reserve", color="#2ca02c")
    ax2.set_ylabel("Cash (EUR)")
    ax2.set_xlabel("Date")
    ax2.legend(loc="upper left", fontsize=8)
    ax2.grid(alpha=0.3)

    filename = f"equity_curve_{strategy_name.replace(' ', '_').lower()}.png"
    plt.tight_layout()
    plt.savefig(filename, dpi=150, bbox_inches="tight")
    print(f"  [Chart saved → {filename}]")


def plot_comparison_equity(results: List[dict], cfg: BacktestConfig) -> None:
    fig, ax = plt.subplots(figsize=(14, 7))
    for row in results:
        equity = row["equity"]
        ax.plot(equity.index, equity["portfolio_value"], label=row["strategy"])
    ax.set_title(f"Strategy Equity Curve Comparison – {cfg.etf_ticker}")
    ax.set_ylabel("Portfolio Value (EUR)")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    filename = f"comparison_equity_{cfg.etf_ticker.replace('.', '_').lower()}.png"
    plt.tight_layout()
    plt.savefig(filename, dpi=150, bbox_inches="tight")
    print(f"  [Comparison chart saved → {filename}]")
