from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional


@dataclass
class Order:
    date: date
    amount_eur: float
    price: float
    units: float
    tier: str
    drawdown: Optional[float] = None
    vix: Optional[float] = None
    cooldown_days: Optional[int] = None


@dataclass
class Trade:
    date: date
    tier: str
    amount_eur: float
    price: float
    units: float
    drawdown: Optional[float] = None
    vix: Optional[float] = None
    cash_left: float = 0.0


@dataclass
class PortfolioSnapshot:
    date: date
    portfolio_value: float
    units: float
    cash_ocf: float
    drawdown: float
    vix: float


@dataclass
class MarketState:
    date: date
    close: float
    drawdown: float
    sma200: float
    vix: float
    is_month_start: bool
    sma20: float = 0.0
    rsi: float = 0.0
    prev_price: float = 0.0
    prev_sma200: float = 0.0
    recovery_days: int = 0


@dataclass
class State:
    cash_ocf: float = 0.0
    units: float = 0.0
    portfolio_value: float = 0.0
    cooldowns: Dict[str, int] = field(default_factory=dict)
    total_contributions: float = 0.0
    total_cashflow: float = 0.0


@dataclass
class KPIReport:
    strategy_name: str
    cagr: float
    twrr: float
    xirr: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    volatility: float
    ulcer_index: float
    final_portfolio_value: float
    total_invested: float
    absolute_return_eur: float
    cash_utilization_rate: float
    time_invested_ratio: float
    number_of_trades: int
    avg_buy_price: float
    total_cashflows: float
    total_trade_costs_eur: float


@dataclass
class SweepResult:
    strategy: str
    parameter_set: Dict[str, float]
    cagr: float
    twrr: float
    xirr: float
    sharpe: float
    sortino: float
    max_dd: float
    final_pv: float
    total_invested: float
    cash_util: float
    trades: int
    total_trade_costs_eur: float


@dataclass
class BacktestResult:
    strategy_name: str
    equity: object
    trades: List[Trade]
    kpis: KPIReport
