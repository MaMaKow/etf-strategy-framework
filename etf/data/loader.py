from __future__ import annotations

import logging
from typing import Tuple

import pandas as pd
import yfinance as yf

from ..config import BacktestConfig


def load_etf_data(cfg: BacktestConfig, logger: logging.Logger) -> Tuple[pd.DataFrame, pd.Series]:
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