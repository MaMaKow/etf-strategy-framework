import matplotlib.pyplot as plt
import pandas as pd
from typing import List

from ..config import SDAConfig
from ..models import KPIReport, Trade


def print_kpi_summary(kpis: KPIReport, cfg: SDAConfig) -> None:
    sep = "─" * 55
    print(f"\n{sep}")
    print(f"  Systematic Drawdown Accumulator v2.0  –  KPI Report")
    print(f"  ETF: {cfg.etf_ticker}   |   {cfg.start_date} → {cfg.end_date}")
    print(sep)
    print(f"  {'CAGR':<35} {kpis.cagr:>10.2%}")
    print(f"  {'Max Drawdown':<35} {kpis.max_drawdown:>10.2%}")
    print(f"  {'Sharpe Ratio':<35} {kpis.sharpe_ratio:>10.3f}")
    print(f"  {'Final Portfolio Value':<35} {kpis.final_portfolio_value:>10,.2f} EUR")
    print(f"  {'Total Invested (savings only)':<35} {kpis.total_invested:>10,.2f} EUR")
    print(f"  {'Absolute Return':<35} {kpis.absolute_return_eur:>10,.2f} EUR")
    print(sep)
    print(f"  {'Dip Buys Executed':<35} {kpis.dip_buys_count:>10d}")
    print(f"  {'Total EUR via Dip Buys':<35} {kpis.total_dip_eur_deployed:>10,.2f} EUR")
    print(f"  {'Cash Utilization Rate':<35} {kpis.cash_utilization_rate:>10.2%}")
    print(f"  {'Avg Dip Buy Price':<35} {kpis.avg_dip_buy_price:>10.4f}")
    print(f"  {'Avg SMA200 (full period)':<35} {kpis.avg_sma200:>10.4f}")
    print(f"  {'OCF Depletion Days (<10% target)':<35} {kpis.ocf_depletion_days:>10d}")
    print(f"{sep}\n")


def plot_equity_curve(equity: pd.DataFrame, trades: List[Trade], cfg: SDAConfig) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True,
                             gridspec_kw={"height_ratios": [3, 1, 1]})
    fig.suptitle(f"SDA v2.0  –  {cfg.etf_ticker}  ({cfg.start_date} → {cfg.end_date})",
                 fontsize=13, fontweight="bold")

    # Panel 1: Equity curve
    ax1 = axes[0]
    ax1.plot(equity.index, equity["portfolio_value"], color="#1a73e8", lw=1.5, label="Portfolio Value")
    ax1.fill_between(equity.index, equity["portfolio_value"], alpha=0.08, color="#1a73e8")

    dip_trades = [t for t in trades if t.tier.startswith("T")]
    if dip_trades:
        dip_df = pd.DataFrame([{"date": pd.to_datetime(t.date), "pv": equity.loc[pd.to_datetime(t.date), "portfolio_value"], "tier": t.tier} for t in dip_trades])
        tier_colors = {"T1": "#2ecc71", "T2": "#f39c12", "T3": "#e74c3c", "T4": "#8e44ad", "T5": "#3498db"}
        for tier, color in tier_colors.items():
            sub = dip_df[dip_df["tier"] == tier]
            if not sub.empty:
                ax1.scatter(sub["date"], sub["pv"], color=color, s=30, zorder=5,
                            label=f"Dip {tier}", alpha=0.8)

    ax1.set_ylabel("Portfolio Value (EUR)")
    ax1.legend(fontsize=8, loc="upper left")
    ax1.grid(alpha=0.3)

    # Panel 2: Drawdown
    ax2 = axes[1]
    ax2.fill_between(equity.index, equity["drawdown"] * 100, 0,
                     color="#e74c3c", alpha=0.5)
    ax2.axhline(-5, color="#f39c12", lw=0.8, ls="--", alpha=0.7)
    ax2.axhline(-10, color="#e67e22", lw=0.8, ls="--", alpha=0.7)
    ax2.axhline(-20, color="#c0392b", lw=0.8, ls="--", alpha=0.7)
    ax2.set_ylabel("Drawdown (%)")
    ax2.grid(alpha=0.3)

    # Panel 3: OCF & VIX
    ax3 = axes[2]
    ax3_twin = ax3.twinx()
    ax3.fill_between(equity.index, equity["cash_ocf"], color="#2ecc71", alpha=0.4, label="OCF")
    ax3.axhline(cfg.ocf_target, color="#27ae60", lw=0.8, ls="--", alpha=0.7)
    ax3.set_ylabel("OCF (EUR)", color="#27ae60")
    ax3_twin.plot(equity.index, equity["vix"], color="#9b59b6", lw=0.7, alpha=0.6, label="VIX")
    ax3_twin.axhline(cfg.vix_threshold, color="#8e44ad", lw=0.8, ls="--", alpha=0.7)
    ax3_twin.set_ylabel("VIX", color="#9b59b6")
    ax3.grid(alpha=0.3)

    plt.tight_layout()
    fname = "sda_equity_curve.png"
    plt.savefig(fname, dpi=150, bbox_inches="tight")
    print(f"  [Chart saved → {fname}]")
    # plt.show()  # Commented out for CLI