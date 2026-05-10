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


@dataclass
class State:
    cash_ocf: float = 0.0
    units: float = 0.0
    portfolio_value: float = 0.0
    cooldowns: Dict[str, int] = field(default_factory=dict)   # tier_label → days left
    total_ocf_inflow: float = 0.0  # Summe aller Sparraten-Anteile, die in den Cash-Puffer gingen


@dataclass
class KPIReport:
    cagr: float
    max_drawdown: float
    sharpe_ratio: float
    final_portfolio_value: float
    total_invested: float
    absolute_return_eur: float
    dip_buys_count: int
    total_dip_eur_deployed: float
    cash_utilization_rate: float
    avg_dip_buy_price: float
    avg_sma200: float
    ocf_depletion_days: int


@dataclass
class SweepResult:
    ocf_target: float
    monthly_savings: float
    vix_threshold: float
    cagr: float
    max_dd: float
    sharpe: float
    final_pv: float
    dip_buys: int
    cash_util: float