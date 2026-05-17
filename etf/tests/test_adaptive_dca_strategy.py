from datetime import datetime

from etf.config import SDAConfig
from etf.models import MarketState
from etf.models import State
from etf.strategies.adaptive_dca import AdaptiveDCAStrategy


def test_monthly_dca_invests_most_cash_with_small_reserve():
    cfg = SDAConfig(monthly_contribution=300.0, adca_reserve_pct=0.10, min_order_eur=50.0)
    strategy = AdaptiveDCAStrategy(cfg)
    state = State(cash_ocf=300.0)

    market = MarketState(
        date=datetime(2024, 1, 1),
        close=100.0,
        drawdown=0.0,
        sma200=95.0,
        vix=20.0,
        is_month_start=True,
    )

    orders = strategy.on_day(market, state)
    assert len(orders) == 1
    assert orders[0].tier == "MONTHLY-DCA"
    assert orders[0].amount_eur == 270.0


def test_dip_buy_uses_fixed_tranche_not_cash_fraction():
    cfg = SDAConfig(min_order_eur=50.0, adca_cooldown_days=0)
    strategy = AdaptiveDCAStrategy(cfg)
    state = State(cash_ocf=120.0)

    market = MarketState(
        date=datetime(2024, 2, 1),
        close=100.0,
        drawdown=-0.12,
        sma200=95.0,
        vix=14.0,
        is_month_start=False,
    )

    orders = strategy.on_day(market, state)
    assert len(orders) == 1
    assert orders[0].tier == "ADCA_T2"
    assert orders[0].amount_eur == 120.0


def test_respects_short_cooldown_with_fallback_to_other_tier():
    cfg = SDAConfig(min_order_eur=50.0, adca_cooldown_days=2)
    strategy = AdaptiveDCAStrategy(cfg)

    state = State(cash_ocf=500.0, cooldowns={"ADCA_T3": 1})
    market = MarketState(
        date=datetime(2024, 3, 1),
        close=100.0,
        drawdown=-0.16,
        sma200=95.0,
        vix=12.0,
        is_month_start=False,
    )

    orders = strategy.on_day(market, state)
    assert len(orders) == 1
    assert orders[0].tier == "ADCA_T2"
