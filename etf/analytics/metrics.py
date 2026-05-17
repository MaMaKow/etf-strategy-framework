from __future__ import annotations

import math
from datetime import datetime
from typing import List, Optional

import numpy as np
import pandas as pd

from ..config import BacktestConfig
from ..models import KPIReport, State, Trade


def _annualize_return(total_return: float, days: int) -> float:
    if days <= 0:
        return 0.0
    return (1.0 + total_return) ** (252.0 / days) - 1.0


def calculate_cagr(equity: pd.Series, cashflows: pd.Series) -> float:
    total_return = calculate_twrr(equity, cashflows)
    days = (equity.index[-1] - equity.index[0]).days
    return _annualize_return(total_return, days)


def calculate_max_drawdown(equity: pd.Series) -> float:
    roll_max = equity.cummax()
    dd = (equity - roll_max) / roll_max
    return float(dd.min())


def calculate_annualized_volatility(equity: pd.Series) -> float:
    daily_ret = equity.pct_change().dropna()
    if daily_ret.empty:
        return 0.0
    return float(daily_ret.std() * math.sqrt(252.0))


def calculate_sharpe(equity: pd.Series, rf: float = 0.02) -> float:
    daily_ret = equity.pct_change().dropna()
    if daily_ret.empty or daily_ret.std() == 0:
        return 0.0
    excess = daily_ret - rf / 252.0
    return float(excess.mean() / excess.std() * math.sqrt(252.0))


def calculate_sortino(equity: pd.Series, rf: float = 0.02) -> float:
    daily_ret = equity.pct_change().dropna()
    if daily_ret.empty:
        return 0.0
    downside = daily_ret[daily_ret < 0.0]
    if downside.empty:
        return float('inf')
    downside_std = downside.std()
    if downside_std == 0:
        return float('inf')
    excess = daily_ret.mean() - rf / 252.0
    return float(excess / downside_std * math.sqrt(252.0))


def calculate_ulcer_index(equity: pd.Series) -> float:
    peak = equity.cummax()
    drawdown = (equity - peak) / peak
    ulcer = np.sqrt((drawdown.clip(upper=0.0) ** 2).mean())
    return float(abs(ulcer))


def calculate_time_invested_ratio(equity: pd.DataFrame) -> float:
    if equity.empty:
        return 0.0
    invested_days = int((equity['units'] > 0).sum())
    return float(invested_days / len(equity))


def calculate_twrr(equity: pd.Series, cashflows: pd.Series) -> float:
    if equity.empty:
        return 0.0

    cashflows = cashflows.reindex(equity.index, fill_value=0.0)
    returns = []
    prev_value = equity.iloc[0]

    for current_date, current_value in equity.iloc[1:].items():
        cashflow = cashflows.loc[current_date]
        if prev_value <= 0:
            prev_value = current_value
            continue
        period_return = (current_value - prev_value - cashflow) / prev_value
        returns.append(period_return)
        prev_value = current_value

    if not returns:
        return 0.0
    total_return = np.prod([1.0 + r for r in returns]) - 1.0
    return float(total_return)


def _xnpv(rate: float, cashflows: List[tuple[datetime, float]]) -> float:
    start = cashflows[0][0]
    total = 0.0
    for when, amount in cashflows:
        year_frac = (when - start).days / 365.25
        total += amount / ((1.0 + rate) ** year_frac)
    return total


def calculate_xirr(cashflows: pd.Series, final_value: Optional[float] = None) -> float:
    flows = []
    for date, amount in cashflows.items():
        if amount == 0.0:
            continue
        flows.append((date.to_pydatetime(), -amount))

    if final_value is not None:
        flows.append((cashflows.index[-1].to_pydatetime(), final_value))

    if len(flows) < 2:
        return 0.0

    try:
        import pyxirr

        return float(pyxirr.xirr({when: amount for when, amount in flows}))
    except Exception:
        pass

    def npv(rate: float) -> float:
        return sum(amount / ((1.0 + rate) ** ((when - flows[0][0]).days / 365.25)) for when, amount in flows)

    def npv_derivative(rate: float) -> float:
        return sum(
            -amount * ((when - flows[0][0]).days / 365.25)
            / ((1.0 + rate) ** (((when - flows[0][0]).days / 365.25) + 1.0))
            for when, amount in flows
        )

    rate = 0.1
    for _ in range(100):
        value = npv(rate)
        derivative = npv_derivative(rate)
        if derivative == 0:
            break
        new_rate = rate - value / derivative
        if abs(rate - new_rate) < 1e-8:
            rate = new_rate
            break
        rate = new_rate
    return float(rate)


def calculate_total_trade_costs(trades: List[Trade], cfg: BacktestConfig) -> float:
    total_costs = 0.0
    for trade in trades:
        if trade.amount_eur <= 0:
            continue
        if trade.tier.startswith("MONTHLY-"):
            continue
        fee = cfg.broker_base_fee_eur + (cfg.broker_variable_fee_rate * trade.amount_eur)
        fee = min(fee, cfg.broker_fee_cap_eur)
        total_costs += fee
    return float(total_costs)


def compute_kpis(equity: pd.DataFrame, trades: List[Trade], final_state: State, cfg: BacktestConfig, strategy_name: str = "strategy") -> KPIReport:
    pv = equity["portfolio_value"]
    cashflows = equity["cashflow"] if "cashflow" in equity.columns else pd.Series(0.0, index=equity.index)
    twrr = calculate_twrr(pv, cashflows)
    cagr = calculate_cagr(pv, cashflows)
    xirr = calculate_xirr(cashflows, float(pv.iloc[-1]))

    avg_buy_price = 0.0
    total_units = 0.0
    if trades:
        total_units = sum(t.units for t in trades if t.units > 0)
        total_amount = sum(t.amount_eur for t in trades if t.units > 0)
        avg_buy_price = (total_amount / total_units) if total_units > 0 else 0.0

    cash_util = 0.0
    if pv.mean() > 0:
        cash_util = 1.0 - float(equity["cash_ocf"].mean() / pv.mean())

    total_trade_costs_eur = calculate_total_trade_costs(trades, cfg)

    return KPIReport(
        strategy_name=strategy_name,
        cagr=cagr,
        twrr=twrr,
        xirr=xirr,
        sharpe_ratio=calculate_sharpe(pv),
        sortino_ratio=calculate_sortino(pv),
        max_drawdown=calculate_max_drawdown(pv),
        volatility=calculate_annualized_volatility(pv),
        ulcer_index=calculate_ulcer_index(pv),
        final_portfolio_value=float(pv.iloc[-1]),
        total_invested=float(final_state.total_contributions),
        absolute_return_eur=float(pv.iloc[-1] - final_state.total_contributions),
        cash_utilization_rate=round(max(0.0, min(cash_util, 1.0)), 4),
        time_invested_ratio=calculate_time_invested_ratio(equity),
        number_of_trades=len(trades),
        avg_buy_price=float(avg_buy_price),
        total_cashflows=float(final_state.total_cashflow),
        total_trade_costs_eur=total_trade_costs_eur,
    )
