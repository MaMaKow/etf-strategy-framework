"""
ETF Buy-the-Dip – Backtesting + Fair Budget Sweep
=================================================

Änderungen:
- Kauf am Folgetag (kein Lookahead-Bias)
- Gebührenmodell integriert
- Robustere Recovery-Logik
- Fairer Budget-Sweep:
    -> identisches Monatsbudget
    -> nicht investiertes Dip-Kapital verfällt
    -> echter Vergleich gegen Sparplan
"""

import os
import uuid
import argparse
import copy
from collections import Counter
from datetime import date

import yfinance as yf
import pandas as pd
import mysql.connector
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# KONFIGURATION
# ---------------------------------------------------------------------------

DB_CONFIG = {
    "host":     "localhost",
    "user":     os.getenv("MARIADB_USER"),
    "password": os.getenv("MARIADB_PASSPHRASE"),
    "database": "etf_bot",
}

ETFS = {
    "SNAW.DE": "IE00BFNM3J75",
    "IUSN.DE": "IE00BF4RFH31",
    "EUNW.DE": "IE0006WW1TQ4",
    "IS3N.DE": "IE00BKM4GZ66",
    "EUNL.DE": "IE00B4L5Y983",
    "IQQY.DE": "IE00B0M63177",
    "EXSA.DE": "DE0002635307",
}

BASE_CONFIG = {

    # Strategie
    "recovery_days": 2,
    "lockout_days": 30,

    # Budgets
    "sparplan_budget": 50,
    "dip_budget": 150,

    # Signale
    "vix_panic":    25,
    "l1_drawdown": -0.10,
    "l1_rsi":       30,
    "l2_rsi":       22,
    "l3_rsi_max":   60,
    "l4_dip_pct":  -0.04,
    "l4_rsi":       32,

    # Gebühren
    "fee_fixed":   1.00,
    "fee_percent": 0.0025,

    # Mindestgröße nach Gebühren
    "min_order_size": 25,
}

TOTAL_MONTHLY_BUDGET = 200

SPARPLAN_MONTHLY_VALUES = list(range(0, 200, 5))

LOGIC_COLORS = {
    "L1_ULTIMATE_DIP": "#d62728",
    "L2_RSI_EXTREME":  "#ff7f0e",
    "L3_TREND_CROSS":  "#2ca02c",
    "L4_MODERATE_DIP": "#9467bd",
}

# ---------------------------------------------------------------------------
# INDIKATOREN
# ---------------------------------------------------------------------------

def calculate_rsi_wilder(series: pd.Series, period: int = 14) -> pd.Series:

    delta = series.diff()

    gain_avg = (
        delta.where(delta > 0, 0.0)
        .ewm(alpha=1 / period, adjust=False)
        .mean()
    )

    loss_avg = (
        (-delta.where(delta < 0, 0.0))
        .ewm(alpha=1 / period, adjust=False)
        .mean()
    )

    rs = gain_avg / loss_avg

    return 100 - (100 / (1 + rs))


def count_consecutive_green(series: pd.Series) -> pd.Series:

    result = [0] * len(series)

    for i in range(1, len(series)):

        if series.iloc[i] > series.iloc[i - 1]:
            result[i] = result[i - 1] + 1
        else:
            result[i] = 0

    return pd.Series(result, index=series.index)


def build_indicators(ticker: str) -> pd.DataFrame | None:

    print(f"  Lade Kursdaten fuer {ticker} ...")

    raw = yf.download(
        ticker,
        period="max",
        auto_adjust=True,
        progress=False,
    )

    if len(raw) < 210:
        print(f"  Zu wenige Daten fuer {ticker}")
        return None

    close = raw["Close"]

    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    df = pd.DataFrame(index=raw.index)

    df["price"] = close

    # Kauf am Folgetag
    df["next_price"] = df["price"].shift(-1)

    df["prev_price"] = df["price"].shift(1)

    df["sma200"] = df["price"].rolling(200).mean()
    df["prev_sma200"] = df["sma200"].shift(1)

    df["sma20"] = df["price"].rolling(20).mean()

    df["ema5"] = df["price"].ewm(span=5, adjust=False).mean()

    df["rsi"] = calculate_rsi_wilder(df["price"])
    df["prev_rsi"] = df["rsi"].shift(1)

    df["high_52w"] = (
        df["price"]
        .rolling(252, min_periods=1)
        .max()
    )

    df["drawdown"] = (
        (df["price"] - df["high_52w"])
        / df["high_52w"]
    )

    df["dip_sma20"] = (
        (df["price"] - df["sma20"])
        / df["sma20"]
    )

    df["recovery"] = count_consecutive_green(df["price"])

    return df.dropna(subset=[
        "sma200",
        "rsi",
        "next_price",
    ])


def load_vix(start: date, end: date) -> pd.Series:

    print("  Lade VIX ...")

    raw = yf.download(
        "^VIX",
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
    )

    if raw.empty:
        return pd.Series(dtype=float)

    return (
        raw["Close"]
        .squeeze()
        .reindex(
            pd.date_range(start, end, freq="B"),
            method="ffill",
        )
    )


def sparplan_dates(trading_days: pd.DatetimeIndex) -> set:

    result = set()
    td_set = set(trading_days)

    for m in pd.period_range(
        trading_days.min(),
        trading_days.max(),
        freq="M",
    ):

        target = pd.Timestamp(m.year, m.month, 1)

        for offset in range(10):

            candidate = target + pd.Timedelta(days=offset)

            if candidate in td_set:
                result.add(candidate)
                break

    return result

# ---------------------------------------------------------------------------
# FEES
# ---------------------------------------------------------------------------

def calculate_fee(amount: float, cfg: dict) -> float:

    return max(
        cfg["fee_fixed"],
        amount * cfg["fee_percent"],
    )

# ---------------------------------------------------------------------------
# SIGNALS
# ---------------------------------------------------------------------------

def check_dip_signal(row: pd.Series, vix: float, cfg: dict) -> str:

    recovering = (
        row["recovery"] >= cfg["recovery_days"]
        and row["rsi"] > row["prev_rsi"]
        and row["price"] > row["ema5"]
    )

    # L1
    if (
        row["drawdown"] <= cfg["l1_drawdown"]
        and row["rsi"]  <  cfg["l1_rsi"]
        and vix         >  cfg["vix_panic"]
        and recovering
    ):
        return "L1_ULTIMATE_DIP"

    # L2
    if (
        row["rsi"] < cfg["l2_rsi"]
        and recovering
    ):
        return "L2_RSI_EXTREME"

    # L3
    if (
        row["price"]          >  row["sma200"]
        and row["prev_price"] <= row["prev_sma200"]
        and row["rsi"]        <  cfg["l3_rsi_max"]
    ):
        return "L3_TREND_CROSS"

    # L4
    if (
        row["dip_sma20"] <= cfg["l4_dip_pct"]
        and row["rsi"]   <  cfg["l4_rsi"]
        and recovering
    ):
        return "L4_MODERATE_DIP"

    return ""

# ---------------------------------------------------------------------------
# SIMULATION
# ---------------------------------------------------------------------------

def simulate(df, vix_series, sp_dates, cfg):

    dip_trades = []
    sparplan_trades = []

    last_dip_date = None

    for ts, row in df.iterrows():

        today = ts.date()

        execution_price = float(row["next_price"])

        vix = float(vix_series.get(ts, 20.0))

        # -------------------------------------------------------
        # SPARPLAN
        # -------------------------------------------------------

        if ts in sp_dates:

            fee = calculate_fee(
                cfg["sparplan_budget"],
                cfg,
            )

            effective_amount = (
                cfg["sparplan_budget"] - fee
            )

            if effective_amount >= cfg["min_order_size"]:

                sparplan_trades.append({
                    "date": today,
                    "price": execution_price,
                    "amount": effective_amount,
                    "fee": fee,
                    "reason": "SPARPLAN",
                })

        # -------------------------------------------------------
        # DIP
        # -------------------------------------------------------

        days_since = (
            (today - last_dip_date).days
            if last_dip_date
            else 999
        )

        if days_since < cfg["lockout_days"]:
            continue

        reason = check_dip_signal(
            row,
            vix,
            cfg,
        )

        if not reason:
            continue

        fee = calculate_fee(
            cfg["dip_budget"],
            cfg,
        )

        effective_amount = (
            cfg["dip_budget"] - fee
        )

        if effective_amount < cfg["min_order_size"]:
            continue

        dip_trades.append({
            "date": today,
            "price": execution_price,
            "amount": effective_amount,
            "fee": fee,
            "reason": reason,
        })

        last_dip_date = today

    return dip_trades, sparplan_trades

# ---------------------------------------------------------------------------
# PERFORMANCE
# ---------------------------------------------------------------------------

def calc_performance(trades, last_price):

    if not trades:
        return {
            "total_invested": 0,
            "units": 0,
            "end_value": 0,
            "fees": 0,
            "n_trades": 0,
        }

    total = sum(t["amount"] for t in trades)

    fees = sum(t["fee"] for t in trades)

    units = sum(
        t["amount"] / t["price"]
        for t in trades
    )

    end_value = units * last_price

    return {
        "total_invested": total,
        "units": units,
        "end_value": end_value,
        "fees": fees,
        "n_trades": len(trades),
    }

# ---------------------------------------------------------------------------
# FAIR SWEEP
# ---------------------------------------------------------------------------

def run_sweep(cache):

    results = []

    n = len(SPARPLAN_MONTHLY_VALUES)

    print(
        f"\n Budget-Sweep: "
        f"{n} Konfigurationen "
        f"x {len(cache)} ETFs\n"
    )

    for i, s_monthly in enumerate(
        SPARPLAN_MONTHLY_VALUES,
        1,
    ):

        d_budget = (
            TOTAL_MONTHLY_BUDGET
            - s_monthly
        )

        cfg = copy.deepcopy(BASE_CONFIG)

        cfg["sparplan_budget"] = s_monthly
        cfg["dip_budget"] = d_budget

        deltas = []

        total_dip_end = 0
        total_sp_end = 0

        for ticker, data in cache.items():

            dip_t, sp_t = simulate(
                data["df"],
                data["vix"],
                data["sp_dates"],
                cfg,
            )

            last_price = float(
                data["df"]["price"].iloc[-1]
            )

            dip = calc_performance(
                dip_t,
                last_price,
            )

            sp = calc_performance(
                sp_t,
                last_price,
            )

            total_dip_end += dip["end_value"]
            total_sp_end += sp["end_value"]

        if total_sp_end > 0:

            avg_delta = (
                (
                    total_dip_end
                    - total_sp_end
                )
                / total_sp_end
                * 100
            )

        else:
            avg_delta = 0

        results.append({
            "sparplan_monthly": s_monthly,
            "dip_budget": d_budget,
            "avg_delta": avg_delta,
            "dip_end": total_dip_end,
            "sp_end": total_sp_end,
        })

        print(
            f"  {i:2d}/{n}: "
            f"Sparplan {s_monthly:3.0f} €/M | "
            f"Dip {d_budget:3.0f} €/Signal "
            f"→ Delta {avg_delta:+.2f}%"
        )

    results.sort(
        key=lambda x: x["avg_delta"],
        reverse=True,
    )

    print("\n\nRanking:\n")

    for rank, r in enumerate(results, 1):

        print(
            f"{rank:2d}. "
            f"Sparplan={r['sparplan_monthly']:>3.0f} € | "
            f"Dip={r['dip_budget']:>3.0f} € | "
            f"Dip-End={r['dip_end']:>9.0f} € | "
            f"SP-End={r['sp_end']:>9.0f} € | "
            f"Delta={r['avg_delta']:+7.2f}%"
        )

# ---------------------------------------------------------------------------
# ENTRY
# ---------------------------------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description="ETF Buy-the-Dip Backtest"
    )

    parser.add_argument(
        "--sweep",
        action="store_true",
    )

    args = parser.parse_args()

    print("\n Lade Marktdaten ...")

    cache = {}

    for ticker, isin in ETFS.items():

        print(f"\n  {ticker}")

        df = build_indicators(ticker)

        if df is None:
            continue

        cache[ticker] = {
            "df": df,
            "vix": load_vix(
                df.index[0].date(),
                df.index[-1].date(),
            ),
            "sp_dates": sparplan_dates(
                df.index
            ),
            "isin": isin,
        }

    if not cache:
        print("Keine Daten geladen.")
        return

    if args.sweep:
        run_sweep(cache)

if __name__ == "__main__":
    main()
