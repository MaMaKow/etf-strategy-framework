import pandas as pd

from ..config import BacktestConfig


def compute_rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))


def compute_recovery_days(series: pd.Series) -> pd.Series:
    streaks = [0] * len(series)
    current = 0
    for i in range(1, len(series)):
        if series.iloc[i] > series.iloc[i - 1]:
            current += 1
        else:
            current = 0
        streaks[i] = current
    return pd.Series(streaks, index=series.index)


def compute_indicators(df: pd.DataFrame, vix: pd.Series, cfg: BacktestConfig) -> pd.DataFrame:
    """Vectorised pre-computation of all strategy signals."""
    df = df.copy()
    close = df["close"]

    df["max_252"] = close.rolling(cfg.rolling_high_window, min_periods=1).max()
    df["drawdown"] = ((close.shift(1) - df["max_252"].shift(1)) / df["max_252"].shift(1))
    df["sma200"] = close.rolling(cfg.sma_window, min_periods=1).mean()
    df["sma20"] = close.rolling(window=20, min_periods=1).mean()
    df["rsi"] = compute_rsi(close, cfg.rsi_window)
    df["prev_price"] = close.shift(1)
    df["prev_sma200"] = df["sma200"].shift(1)
    df["recovery_days"] = compute_recovery_days(close)
    df["vix"] = vix
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