import pandas as pd

from ..config import BacktestConfig


def compute_indicators(df: pd.DataFrame, vix: pd.Series, cfg: BacktestConfig) -> pd.DataFrame:
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