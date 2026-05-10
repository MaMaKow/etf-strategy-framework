import math
import numpy as np
import pandas as pd
from typing import List

from ..config import SDAConfig
from ..models import KPIReport, State, Trade
from ..portfolio.portfolio import Portfolio


def calculate_cagr(equity: pd.Series) -> float:
    active = equity[equity > 0]
    if active.empty or len(active) < 2:
        return 0.0
    years = (active.index[-1] - active.index[0]).days / 365.25
    if years <= 0:
        return 0.0
    return (active.iloc[-1] / active.iloc[0]) ** (1 / years) - 1


def calculate_max_drawdown(equity: pd.Series) -> float:
    roll_max = equity.cummax()
    dd = (equity - roll_max) / roll_max
    return float(dd.min())


def calculate_sharpe(equity: pd.Series, rf: float = 0.02) -> float:
    daily_ret = equity.pct_change().dropna()
    excess = daily_ret - rf / 252
    if excess.std() == 0:
        return float("nan")
    return float(excess.mean() / excess.std() * math.sqrt(252))


def compute_kpis(equity: pd.DataFrame, trades: List[Trade], final_state: State, cfg: SDAConfig) -> KPIReport:
    pv = equity["portfolio_value"]

    # Total invested
    total_months = (
        (equity.index[-1].year - equity.index[0].year) * 12
        + equity.index[-1].month - equity.index[0].month + 1
    )
    total_invested = total_months * cfg.monthly_savings

    # Dip trades only
    dip_trades = [t for t in trades if t.tier.startswith("T")]

    # Cash utilization
    total_dip_eur = sum(t.amount_eur for t in dip_trades)
    cash_util = total_dip_eur / final_state.total_ocf_inflow if final_state.total_ocf_inflow > 0 else 0.0

    # Average dip buy price vs SMA200
    dip_prices = [t.price for t in dip_trades if t.price]
    avg_dip_price = float(np.mean(dip_prices)) if dip_prices else float("nan")

    # Approximate average SMA200
    avg_sma200 = float(equity["close"].rolling(200, min_periods=1).mean().mean())

    # OCF depletion
    ocf_depletion_days = int((equity["cash_ocf"] < 0.10 * cfg.ocf_target).sum())

    return KPIReport(
        cagr=calculate_cagr(pv),
        max_drawdown=calculate_max_drawdown(pv),
        sharpe_ratio=calculate_sharpe(pv),
        final_portfolio_value=float(pv.iloc[-1]),
        total_invested=total_invested,
        absolute_return_eur=float(pv.iloc[-1]) - total_invested,
        dip_buys_count=len(dip_trades),
        total_dip_eur_deployed=total_dip_eur,
        cash_utilization_rate=cash_util,
        avg_dip_buy_price=avg_dip_price,
        avg_sma200=avg_sma200,
        ocf_depletion_days=ocf_depletion_days,
    )