"""
etf_sda_backtest.py
Systematic Drawdown Accumulator (SDA v2.0)
Path-dependent cashflow state machine backtest engine.
"""

from __future__ import annotations

import csv
import logging
import math
import sys
import warnings
from dataclasses import dataclass, field
from datetime import date
from itertools import product as iterproduct
from typing import Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SDAConfig:
    # ── Universe ─────────────────────────────────────────────────────────────
    etf_ticker: str = "EUNL.DE"
    vix_ticker: str = "^VIX"
    start_date: str = "2014-01-01"
    end_date: str = "2024-12-31"

    # ── Cash-flow ────────────────────────────────────────────────────────────
    monthly_savings: float = 1000.0          # EUR per month
    ocf_target: float = 5000.0              # target OCF reserve

    # ── Monthly allocation thresholds ────────────────────────────────────────
    ocf_low_pct: float = 0.30               # below → 100 % to OCF
    ocf_mid_pct: float = 1.00               # below → 70 % ETF / 30 % OCF

    # ── Dip Buy tiers ────────────────────────────────────────────────────────
    # (drawdown_threshold, ocf_fraction, label)
    dip_tiers: List[Tuple[float, float, str]] = field(default_factory=lambda: [
        (-0.05, 0.20, "T1"),
        (-0.10, 0.30, "T2"),
        (-0.20, 0.40, "T3"),
        (-0.30, 0.50, "T4"),
        (-0.40, 0.60, "T5")
    ])

    # ── Filters ──────────────────────────────────────────────────────────────
    vix_threshold: float = 15.0
    t1_requires_above_sma200: bool = True

    # ── Cooldown ─────────────────────────────────────────────────────────────
    cooldown_min: int = 5

    # ── Execution ────────────────────────────────────────────────────────────
    min_order_eur: float = 500.0
    slippage: float = 0.0005                # 0.05 %

    # ── Indicators ───────────────────────────────────────────────────────────
    rolling_high_window: int = 252
    sma_window: int = 200

    # ── Misc ─────────────────────────────────────────────────────────────────
    seed: int = 42
    log_level: str = "INFO"
    export_trades_csv: str = "sda_trades.csv"


# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────

def _setup_logging(level: str) -> logging.Logger:
    logger = logging.getLogger("SDA")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                         datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(h)
    return logger


# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADER
# ─────────────────────────────────────────────────────────────────────────────

def data_loader(cfg: SDAConfig, logger: logging.Logger) -> Tuple[pd.DataFrame, pd.Series]:
    """Download ETF and VIX daily close prices."""
    logger.info("Downloading ETF data: %s  [%s → %s]", cfg.etf_ticker, cfg.start_date, cfg.end_date)
    raw_etf = yf.download(
        cfg.etf_ticker,
        start=cfg.start_date,
        end=cfg.end_date,
        auto_adjust=True,
        progress=False,
    )
    if raw_etf.empty:
        raise ValueError(f"No data returned for {cfg.etf_ticker}")

    close = raw_etf["Close"].squeeze().dropna()
    close.index = pd.to_datetime(close.index).tz_localize(None)
    close.name = "close"

    logger.info("Downloading VIX data: %s", cfg.vix_ticker)
    raw_vix = yf.download(
        cfg.vix_ticker,
        start=cfg.start_date,
        end=cfg.end_date,
        auto_adjust=True,
        progress=False,
    )
    vix_close: pd.Series
    if raw_vix.empty:
        logger.warning("VIX data unavailable – using constant 20 (always above threshold)")
        vix_close = pd.Series(20.0, index=close.index, name="vix")
    else:
        vix_close = raw_vix["Close"].squeeze().dropna()
        vix_close.index = pd.to_datetime(vix_close.index).tz_localize(None)
        vix_close.name = "vix"
        vix_close = vix_close.reindex(close.index).ffill().fillna(20.0)

    logger.info("ETF rows: %d  |  Date range: %s – %s",
                len(close), close.index[0].date(), close.index[-1].date())
    return close.to_frame(), vix_close


# ─────────────────────────────────────────────────────────────────────────────
# INDICATORS
# ─────────────────────────────────────────────────────────────────────────────

def compute_indicators(df: pd.DataFrame, vix: pd.Series, cfg: SDAConfig) -> pd.DataFrame:
    """Vectorised pre-computation of all strategy signals."""
    df = df.copy()
    close = df["close"]

    df["max_252"]     = close.rolling(cfg.rolling_high_window, min_periods=1).max()
    df["drawdown"]    = ((df["close"].shift(1) - df["max_252"].shift(1)) / df["max_252"].shift(1))
    df["sma200"]      = close.rolling(cfg.sma_window, min_periods=1).mean()
    df["sma200_signal"] = df["sma200"].shift(1)
    df["vix"]         = vix
    df["vix_signal"]  = vix.shift(1)                    # yesterday's VIX
    df["is_month_start"] = (
        pd.Series(close.index, index=close.index)
        .apply(lambda d: d)
        .diff()
        .dt.days.fillna(1) >= 1
    )
    # True on first trading day of each calendar month
    df["month"] = close.index.to_period("M")
    df["is_month_start"] = df["month"] != df["month"].shift(1)

    return df.drop(columns=["month"])


# ─────────────────────────────────────────────────────────────────────────────
# STATE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class State:
    cash_ocf: float = 0.0
    units: float = 0.0
    portfolio_value: float = 0.0
    cooldowns: Dict[str, int] = field(default_factory=dict)   # tier_label → days left
    total_ocf_inflow: float = 0.0  # Summe aller Sparraten-Anteile, die in den Cash-Puffer gingen


# ─────────────────────────────────────────────────────────────────────────────
# EXECUTION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _apply_slippage(price: float, slippage: float) -> float:
    return price * (1.0 + slippage)


def _cooldown_days(drawdown: float, cooldown_min: int) -> int:
    raw = int(20 * math.exp(3 * drawdown))
    return max(cooldown_min, raw)


def execute_signals(
    state: State,
    row: pd.Series,
    cfg: SDAConfig,
    logger: logging.Logger,
    trades: List[dict],
) -> None:
    """
    Evaluate dip-buy triggers for a single day and mutate state in-place.
    All cooldowns are decremented BEFORE signal evaluation.
    """
    price_raw: float = float(row["close"])
    dd: float = float(row["drawdown"])
    vix_sig: float = float(row["vix_signal"])
    sma200: float = float(row["sma200"])
    dt: date = row.name.date()

    # ── Decrement active cooldowns ────────────────────────────────────────────
    spent = []
    for lbl in list(state.cooldowns):
        state.cooldowns[lbl] -= 1
        if state.cooldowns[lbl] <= 0:
            spent.append(lbl)
    for lbl in spent:
        del state.cooldowns[lbl]

    # ── VIX filter ────────────────────────────────────────────────────────────
    if vix_sig <= cfg.vix_threshold:
        return
    if math.isnan(vix_sig):
        return

    # ── Evaluate tiers (deepest first for cooldown precedence) ───────────────
    for threshold, ocf_frac, label in reversed(cfg.dip_tiers):
        if dd > threshold:
            continue                                        # not deep enough
        if label in state.cooldowns:
            continue                                        # still cooling down
        if label == "T1" and cfg.t1_requires_above_sma200:
            if price_raw <= sma200:
                continue

        amount_eur = ocf_frac * state.cash_ocf
        if amount_eur < cfg.min_order_eur:
            continue                                        # below minimum order

        exec_price = _apply_slippage(price_raw, cfg.slippage)
        units_bought = amount_eur / exec_price
        state.cash_ocf -= amount_eur
        state.units += units_bought

        cd = _cooldown_days(dd, cfg.cooldown_min)
        state.cooldowns[label] = cd

        logger.info(
            "BUY  | %s | %-3s | %9.2f EUR | Price %8.4f | OCF left %9.2f | CD %d days",
            dt, label, amount_eur, exec_price, state.cash_ocf, cd,
        )
        trades.append({
            "date":       dt,
            "tier":       label,
            "amount_eur": round(amount_eur, 4),
            "price":      round(exec_price, 6),
            "units":      round(units_bought, 6),
            "drawdown":   round(dd, 6),
            "vix":        round(vix_sig, 2),
            "cash_left":  round(state.cash_ocf, 4),
        })
        # Only one tier per day (deepest triggered wins)
        break


# ─────────────────────────────────────────────────────────────────────────────
# MONTHLY SAVINGS LOGIC
# ─────────────────────────────────────────────────────────────────────────────

def _apply_monthly_savings(
    state: State,
    price: float,
    cfg: SDAConfig,
    logger: logging.Logger,
    dt: date,
    trades: List[dict],
) -> None:
    savings = cfg.monthly_savings
    ocf = state.cash_ocf
    target = cfg.ocf_target

    if ocf < cfg.ocf_low_pct * target:
        # 100 % → OCF
        state.cash_ocf += savings
        state.total_ocf_inflow += savings # NEU
        logger.debug("%s | Monthly savings → OCF (%.0f EUR) | OCF now %.2f", dt, savings, state.cash_ocf)
    elif ocf < cfg.ocf_mid_pct * target:
        # 70 % ETF, 30 % OCF
        etf_part = 0.70 * savings
        ocf_part = 0.30 * savings
        state.cash_ocf += ocf_part
        state.total_ocf_inflow += ocf_part # NEU
        if etf_part >= cfg.min_order_eur:
            exec_price = _apply_slippage(price, cfg.slippage)
            units_bought = etf_part / exec_price
            state.units += units_bought
            logger.debug("%s | Monthly 70/30 → ETF %.2f EUR @ %.4f | OCF %.2f",
                         dt, etf_part, exec_price, state.cash_ocf)
            trades.append({
                "date": dt, "tier": "MONTHLY-ETF",
                "amount_eur": round(etf_part, 4),
                "price": round(exec_price, 6),
                "units": round(units_bought, 6),
                "drawdown": None, "vix": None,
                "cash_left": round(state.cash_ocf, 4),
            })
        else:
            state.cash_ocf += etf_part          # too small → park in OCF
    else:
        # 100 % ETF
        if savings >= cfg.min_order_eur:
            exec_price = _apply_slippage(price, cfg.slippage)
            units_bought = savings / exec_price
            state.units += units_bought
            logger.debug("%s | Monthly 100%% ETF %.2f EUR @ %.4f",
                         dt, savings, exec_price)
            trades.append({
                "date": dt, "tier": "MONTHLY-ETF",
                "amount_eur": round(savings, 4),
                "price": round(exec_price, 6),
                "units": round(units_bought, 6),
                "drawdown": None, "vix": None,
                "cash_left": round(state.cash_ocf, 4),
            })
        else:
            state.cash_ocf += savings


# ─────────────────────────────────────────────────────────────────────────────
# CORE BACKTEST LOOP
# ─────────────────────────────────────────────────────────────────────────────

def run_backtest(
    df: pd.DataFrame,
    cfg: SDAConfig,
    logger: logging.Logger,
) -> Tuple[pd.DataFrame, List[dict]]:
    """
    Path-dependent cashflow state machine.
    Iterates row-by-row; state mutated in-place.
    Returns equity curve DataFrame and trade log.
    """
    state = State()
    trades: List[dict] = []
    equity_rows: List[dict] = []

    n = len(df)
    logger.info("Starting simulation: %d trading days", n)

    for i, (idx, row) in enumerate(df.iterrows()):
        price = float(row["close"])

        # ── Monthly savings injection ─────────────────────────────────────────
        if bool(row["is_month_start"]):
            _apply_monthly_savings(state, price, cfg, logger, idx.date(), trades)

        # ── Dip buy evaluation ────────────────────────────────────────────────
        execute_signals(state, row, cfg, logger, trades)

        # ── Daily portfolio mark-to-market ────────────────────────────────────
        state.portfolio_value = state.units * price + state.cash_ocf

        equity_rows.append({
            "date":            idx,
            "close":           price,
            "portfolio_value": state.portfolio_value,
            "units":           state.units,
            "cash_ocf":        state.cash_ocf,
            "drawdown":        float(row["drawdown"]),
            "vix":             float(row["vix"]),
        })

        if (i + 1) % 250 == 0 or (i + 1) == n:
            logger.info("Progress: %d / %d  |  PV: %.2f EUR  |  Units: %.4f  |  OCF: %.2f",
                        i + 1, n, state.portfolio_value, state.units, state.cash_ocf)

    equity = pd.DataFrame(equity_rows).set_index("date")
    return equity, trades, state  # Rückgabe um state erweitern

# ─────────────────────────────────────────────────────────────────────────────
# KPI ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def _cagr(equity: pd.Series) -> float:
    # Nur Daten berücksichtigen, ab denen Kapital vorhanden ist
    active = equity[equity > 0]
    if active.empty or len(active) < 2:
        return 0.0
    
    years = (active.index[-1] - active.index[0]).days / 365.25
    if years <= 0:
        return 0.0
    return (active.iloc[-1] / active.iloc[0]) ** (1 / years) - 1

def _max_drawdown(equity: pd.Series) -> float:
    roll_max = equity.cummax()
    dd = (equity - roll_max) / roll_max
    return float(dd.min())


def _sharpe(equity: pd.Series, rf: float = 0.02) -> float:
    daily_ret = equity.pct_change().dropna()
    excess = daily_ret - rf / 252
    if excess.std() == 0:
        return float("nan")
    return float(excess.mean() / excess.std() * math.sqrt(252))


def compute_kpis(equity: pd.DataFrame, trades: List[dict], state: State, cfg: SDAConfig) -> dict:
    pv = equity["portfolio_value"]

    # Total invested
    total_months = (
        (equity.index[-1].year - equity.index[0].year) * 12
        + equity.index[-1].month - equity.index[0].month + 1
    )
    total_invested = total_months * cfg.monthly_savings

    # Dip trades only
    dip_trades = [t for t in trades if t["tier"].startswith("T")]

    # Cash utilization: total EUR deployed via dip buys / total OCF ever accumulated
    total_dip_eur = sum(t["amount_eur"] for t in dip_trades)
    cash_util = total_dip_eur / state.total_ocf_inflow if state.total_ocf_inflow > 0 else 0.0

    # Average dip buy price vs SMA200
    dip_prices = [t["price"] for t in dip_trades if t.get("price")]
    avg_dip_price = float(np.mean(dip_prices)) if dip_prices else float("nan")

    # Approximate average SMA200 at dip buy dates
    avg_sma200 = float(equity["close"].rolling(200, min_periods=1).mean().mean())

    # OCF depletion: days where OCF < 10 % of target
    ocf_depletion_days = int((equity["cash_ocf"] < 0.10 * cfg.ocf_target).sum())

    return {
        "CAGR":                   _cagr(pv),
        "Max Drawdown":           _max_drawdown(pv),
        "Sharpe Ratio":           _sharpe(pv),
        "Final Portfolio Value":  float(pv.iloc[-1]),
        "Total Invested":         total_invested,
        "Absolute Return EUR":    float(pv.iloc[-1]) - total_invested,
        "Dip Buys Count":         len(dip_trades),
        "Total Dip EUR Deployed": total_dip_eur,
        "Cash Utilization Rate":  cash_util,
        "Avg Dip Buy Price":      avg_dip_price,
        "Avg SMA200":             avg_sma200,
        "OCF Depletion Days":     ocf_depletion_days,
    }


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT / REPORTING
# ─────────────────────────────────────────────────────────────────────────────

def print_kpi_summary(kpis: dict, cfg: SDAConfig) -> None:
    sep = "─" * 55
    print(f"\n{sep}")
    print(f"  Systematic Drawdown Accumulator v2.0  –  KPI Report")
    print(f"  ETF: {cfg.etf_ticker}   |   {cfg.start_date} → {cfg.end_date}")
    print(sep)
    print(f"  {'CAGR':<35} {kpis['CAGR']:>10.2%}")
    print(f"  {'Max Drawdown':<35} {kpis['Max Drawdown']:>10.2%}")
    print(f"  {'Sharpe Ratio':<35} {kpis['Sharpe Ratio']:>10.3f}")
    print(f"  {'Final Portfolio Value':<35} {kpis['Final Portfolio Value']:>10,.2f} EUR")
    print(f"  {'Total Invested (savings only)':<35} {kpis['Total Invested']:>10,.2f} EUR")
    print(f"  {'Absolute Return':<35} {kpis['Absolute Return EUR']:>10,.2f} EUR")
    print(sep)
    print(f"  {'Dip Buys Executed':<35} {kpis['Dip Buys Count']:>10d}")
    print(f"  {'Total EUR via Dip Buys':<35} {kpis['Total Dip EUR Deployed']:>10,.2f} EUR")
    print(f"  {'Cash Utilization Rate':<35} {kpis['Cash Utilization Rate']:>10.2%}")
    print(f"  {'Avg Dip Buy Price':<35} {kpis['Avg Dip Buy Price']:>10.4f}")
    print(f"  {'Avg SMA200 (full period)':<35} {kpis['Avg SMA200']:>10.4f}")
    print(f"  {'OCF Depletion Days (<10% target)':<35} {kpis['OCF Depletion Days']:>10d}")
    print(f"{sep}\n")


def plot_equity_curve(equity: pd.DataFrame, trades: List[dict], cfg: SDAConfig) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True,
                             gridspec_kw={"height_ratios": [3, 1, 1]})
    fig.suptitle(f"SDA v2.0  –  {cfg.etf_ticker}  ({cfg.start_date} → {cfg.end_date})",
                 fontsize=13, fontweight="bold")

    # ── Panel 1: Equity curve ─────────────────────────────────────────────────
    ax1 = axes[0]
    ax1.plot(equity.index, equity["portfolio_value"], color="#1a73e8", lw=1.5, label="Portfolio Value")
    ax1.fill_between(equity.index, equity["portfolio_value"], alpha=0.08, color="#1a73e8")

    dip_trade_df = pd.DataFrame([t for t in trades if t["tier"].startswith("T")])
    if not dip_trade_df.empty:
        dip_trade_df["date"] = pd.to_datetime(dip_trade_df["date"])
        dip_trade_df = dip_trade_df.merge(
            equity[["portfolio_value"]].rename(columns={"portfolio_value": "pv"}),
            left_on="date", right_index=True, how="left",
        )
        tier_colors = {"T1": "#2ecc71", "T2": "#f39c12", "T3": "#e74c3c", "T4": "#8e44ad", "T5": "#3498db"}
        for tier, color in tier_colors.items():
            sub = dip_trade_df[dip_trade_df["tier"] == tier]
            if not sub.empty:
                ax1.scatter(sub["date"], sub["pv"], color=color, s=30, zorder=5,
                            label=f"Dip {tier}", alpha=0.8)

    ax1.set_ylabel("Portfolio Value (EUR)")
    ax1.legend(fontsize=8, loc="upper left")
    ax1.grid(alpha=0.3)

    # ── Panel 2: Drawdown ─────────────────────────────────────────────────────
    ax2 = axes[1]
    ax2.fill_between(equity.index, equity["drawdown"] * 100, 0,
                     color="#e74c3c", alpha=0.5)
    ax2.axhline(-5, color="#f39c12", lw=0.8, ls="--", alpha=0.7)
    ax2.axhline(-10, color="#e67e22", lw=0.8, ls="--", alpha=0.7)
    ax2.axhline(-20, color="#c0392b", lw=0.8, ls="--", alpha=0.7)
    ax2.set_ylabel("Drawdown (%)")
    ax2.grid(alpha=0.3)

    # ── Panel 3: OCF & VIX ───────────────────────────────────────────────────
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
    plt.show()


def export_trades_csv(trades: List[dict], path: str) -> None:
    if not trades:
        return
    keys = ["date", "tier", "amount_eur", "price", "units", "drawdown", "vix", "cash_left"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(trades)
    print(f"  [Trade log saved → {path}]")


# ─────────────────────────────────────────────────────────────────────────────
# PARAMETER SWEEP
# ─────────────────────────────────────────────────────────────────────────────

def parameter_sweep(
    base_cfg: SDAConfig,
    logger: logging.Logger,
    ocf_targets: Optional[List[float]] = None,
    monthly_savings_list: Optional[List[float]] = None,
    vix_thresholds: Optional[List[float]] = None,
) -> pd.DataFrame:
    """
    Grid sweep over OCF target, monthly savings, and VIX threshold.
    Returns DataFrame sorted by Sharpe.
    """
    ocf_targets = ocf_targets or [3000.0, 5000.0, 8000.0]
    monthly_savings_list = monthly_savings_list or [500.0, 1000.0, 2000.0]
    vix_thresholds = vix_thresholds or [12.0, 15.0, 20.0]

    combos = list(iterproduct(ocf_targets, monthly_savings_list, vix_thresholds))
    logger.info("Parameter sweep: %d combinations", len(combos))

    # Pre-download data once
    df_raw, vix_series = data_loader(base_cfg, logger)
    df_ind = compute_indicators(df_raw, vix_series, base_cfg)

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

        equity_i, trades_i, final_state_i = run_backtest(df_ind.copy(), cfg_i, sweep_logger)
        kpis_i = compute_kpis(equity_i, trades_i, final_state_i, cfg_i)

        results.append({
            "ocf_target":     ocf_t,
            "monthly_savings": savings,
            "vix_threshold":  vix_t,
            "CAGR":           kpis_i["CAGR"],
            "Max_DD":         kpis_i["Max Drawdown"],
            "Sharpe":         kpis_i["Sharpe Ratio"],
            "Final_PV":       kpis_i["Final Portfolio Value"],
            "Dip_Buys":       kpis_i["Dip Buys Count"],
            "Cash_Util":      kpis_i["Cash Utilization Rate"],
        })
        logger.info("Sweep %d/%d  OCF=%.0f  Sav=%.0f  VIX=%.0f  → Sharpe %.3f",
                    i + 1, len(combos), ocf_t, savings, vix_t, kpis_i["Sharpe Ratio"])

    result_df = pd.DataFrame(results).sort_values("Sharpe", ascending=False).reset_index(drop=True)
    return result_df


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

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

    logger = _setup_logging(cfg.log_level)

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

    # ── Load & prepare data ───────────────────────────────────────────────────
    df_raw, vix_series = data_loader(cfg, logger)
    df = compute_indicators(df_raw, vix_series, cfg)

    # ── Run simulation ────────────────────────────────────────────────────────
    #equity, trades = run_backtest(df, cfg, logger)
    equity, trades, final_state = run_backtest(df, cfg, logger)

    # ── KPIs ─────────────────────────────────────────────────────────────────
    kpis = compute_kpis(equity, trades, final_state, cfg) # final_state übergeben
    print_kpi_summary(kpis, cfg)

    # ── Export trades ─────────────────────────────────────────────────────────
    if cfg.export_trades_csv:
        export_trades_csv(trades, cfg.export_trades_csv)

    # ── Plot ──────────────────────────────────────────────────────────────────
    plot_equity_curve(equity, trades, cfg)

    # ── Optional parameter sweep ──────────────────────────────────────────────
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
    # Pass --sweep to enable parameter grid search
    _sweep = "--sweep" in sys.argv
    main(run_sweep=_sweep)
