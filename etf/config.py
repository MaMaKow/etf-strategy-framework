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
    monthly_contribution: float = 1000.0     # EUR per month
    initial_cash: float = 0.0                # starting cash balance
    min_order_eur: float = 250.0             # war vorher 500.0
    slippage: float = 0.0005                # 0.05 %

    # ── Value Averaging ──────────────────────────────────────────────────────
    value_averaging_mode: str = "linear"   # linear or exponential
    value_averaging_base: Optional[float] = None
    value_averaging_growth_rate: float = 0.0
    value_averaging_allow_negative: bool = False

    # ── Indicators ───────────────────────────────────────────────────────────
    rolling_high_window: int = 252
    sma_window: int = 200

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
    monthly_savings: Optional[float] = None         # legacy alias for monthly contribution
    ocf_target: float = 5000.0
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
        else:
            self.monthly_contribution = self.monthly_savings
        self.value_averaging_base = self.monthly_contribution
