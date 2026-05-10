from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class SDAConfig:
    # ── Universe ─────────────────────────────────────────────────────────────
    etf_ticker: str = "EUNL.DE"
    vix_ticker: str = "^VIX"
    start_date: str = "2014-01-01"
    end_date: str = "2024-12-31"

    # ── Cash-flow ────────────────────────────────────────────────────────────
    monthly_savings: float = 1000.0          # EUR per month
    ocf_target: float = 5000.0              # target OCF reserve

    # ── Monthly allocation thresholds ────────────────────────────────────────
    ocf_low_pct: float = 0.30               # below → 100 % to OCF
    ocf_mid_pct: float = 1.00               # below → 70 % ETF / 30 % OCF

    # ── Dip Buy tiers ────────────────────────────────────────────────────────
    # (drawdown_threshold, ocf_fraction, label)
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

    # ── Execution ────────────────────────────────────────────────────────────
    min_order_eur: float = 500.0
    slippage: float = 0.0005                # 0.05 %

    # ── Indicators ───────────────────────────────────────────────────────────
    rolling_high_window: int = 252
    sma_window: int = 200

    # ── Misc ─────────────────────────────────────────────────────────────────
    seed: int = 42
    log_level: str = "INFO"
    export_trades_csv: str = "sda_trades.csv"