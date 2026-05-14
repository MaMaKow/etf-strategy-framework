from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class BacktestConfig:
    # ── Universe ─────────────────────────────────────────────────────────────
    etf_ticker: str = "EUNL.DE"
    vix_ticker: str = "^VIX"
    start_date: str = "2014-01-01"
    end_date: str = "2024-12-31"

    # ── Cash-flow / Execution ─────────────────────────────────────────────────
    monthly_contribution: float = 150.0     # EUR per month
    initial_cash: float = 0.0                # starting cash balance
    min_order_eur: float = 100.0             # default optimized order size
    slippage: float = 0.0005                # 0.05 %

    # ── Value Averaging ──────────────────────────────────────────────────────
    value_averaging_mode: str = "linear"   # linear or exponential
    value_averaging_base: Optional[float] = None
    value_averaging_growth_rate: float = 0.0
    value_averaging_allow_negative: bool = False

    # ── Indicators ───────────────────────────────────────────────────────────
    rolling_high_window: int = 252
    sma_window: int = 200
    rsi_window: int = 14

    # ── Bot signal parameters ──────────────────────────────────────────────────
    recovery_days: int = 2
    min_days_l1l2: int = 30
    min_days_l3: int = 60
    min_days_l4: int = 30
    l1_drawdown: float = -0.10
    l1_rsi: float = 30.0
    l1_amount: float = 100.0
    l2_rsi: float = 22.0
    l2_amount: float = 50.0
    l3_rsi_max: float = 40.0
    l3_amount: float = 50.0
    l4_dip_pct: float = -0.04
    l4_rsi: float = 32.0
    l4_amount: float = 25.0
    drawdown_scale_factor: float = 2.0

    # ── Misc ─────────────────────────────────────────────────────────────────
    seed: int = 42
    log_level: str = "INFO"
    export_trades_csv: str = ""

    def __post_init__(self):
        if self.value_averaging_base is None:
            self.value_averaging_base = self.monthly_contribution
        if self.value_averaging_base <= 0:
            self.value_averaging_base = self.monthly_contribution


@dataclass
class SDAConfig(BacktestConfig):
    monthly_savings: Optional[float] = None         # amount invested in the monthly ETF order; if None, defaults to monthly_contribution
    ocf_target: float = 100.0
    ocf_low_pct: float = 0.30               # below → 100 % to OCF
    ocf_mid_pct: float = 1.00               # below → 70 % ETF / 30 % OCF

    # ── Dip Buy tiers ────────────────────────────────────────────────────────
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

    def __post_init__(self):
        super().__post_init__()
        if self.monthly_savings is None:
            self.monthly_savings = self.monthly_contribution
        self.value_averaging_base = self.monthly_contribution
