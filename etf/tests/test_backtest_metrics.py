import logging
from datetime import datetime

import pandas as pd

from ..analytics.metrics import calculate_twrr, calculate_xirr
from ..backtest.engine import BacktestEngine
from ..config import BacktestConfig, SDAConfig
from ..models import State
from ..strategies.dca import DollarCostAveragingStrategy
from ..strategies.sda import SDAStrategy
from ..strategies.value_averaging import ValueAveragingStrategy


def test_dca_generates_monthly_order():
    cfg = BacktestConfig(monthly_contribution=1000.0, min_order_eur=100.0, slippage=0.0)
    strategy = DollarCostAveragingStrategy(cfg)
    state = State(cash_ocf=1000.0)
    market_state = type("MS", (), {
        "date": datetime(2020, 1, 2).date(),
        "close": 100.0,
        "drawdown": 0.0,
        "sma200": 100.0,
        "vix": 20.0,
        "is_month_start": True,
    })

    orders = strategy.on_day(market_state, state)
    assert len(orders) == 1
    assert orders[0].amount_eur == 1000.0
    assert orders[0].tier == "MONTHLY-DCA"


def test_sda_dip_buy_trigger():
    cfg = SDAConfig(
        monthly_savings=1000.0,
        ocf_target=5000.0,
        min_order_eur=100.0,
        slippage=0.0,
        vix_threshold=15.0,
        ocf_low_pct=0.3,
        ocf_mid_pct=1.0,
        dip_tiers=[(-0.05, 0.20, "T1"), (-0.10, 0.30, "T2")],
        t1_requires_above_sma200=False,
    )
    strategy = SDAStrategy(cfg)
    state = State(cash_ocf=5000.0)

    market_state = type("MS", (), {
        "date": datetime(2020, 1, 2).date(),
        "close": 100.0,
        "drawdown": -0.10,
        "sma200": 90.0,
        "vix": 20.0,
        "is_month_start": True,
    })

    orders = strategy.on_day(market_state, state)
    assert any(order.tier in {"T1", "T2"} for order in orders)


def test_value_averaging_target_values():
    cfg = BacktestConfig(monthly_contribution=1000.0, min_order_eur=100.0, slippage=0.0, value_averaging_mode="linear", value_averaging_base=1000.0)
    strategy = ValueAveragingStrategy(cfg)
    assert strategy._target_value(1) == 1000.0
    assert strategy._target_value(3) == 3000.0

    cfg2 = BacktestConfig(monthly_contribution=1000.0, min_order_eur=100.0, slippage=0.0, value_averaging_mode="exponential", value_averaging_base=1000.0, value_averaging_growth_rate=0.1)
    strategy2 = ValueAveragingStrategy(cfg2)
    assert strategy2._target_value(1) == 1100.0


def test_value_averaging_invests_first_month():
    cfg = BacktestConfig(monthly_contribution=1000.0, min_order_eur=100.0, slippage=0.0, value_averaging_mode="linear", value_averaging_base=None)
    strategy = ValueAveragingStrategy(cfg)
    state = State(cash_ocf=1000.0)
    market_state = type("MS", (), {
        "date": datetime(2020, 1, 2).date(),
        "close": 100.0,
        "drawdown": 0.0,
        "sma200": 100.0,
        "vix": 20.0,
        "is_month_start": True,
    })

    orders = strategy.on_day(market_state, state)
    assert len(orders) == 1
    assert orders[0].amount_eur == 1000.0
    assert orders[0].tier == "MONTHLY-VA"


def test_slippage_applies_to_order_price():
    cfg = BacktestConfig(monthly_contribution=1000.0, slippage=0.01, min_order_eur=100.0)
    strategy = DollarCostAveragingStrategy(cfg)
    state = State(cash_ocf=1000.0)
    market_state = type("MS", (), {"date": datetime(2020, 1, 2).date(), "close": 100.0, "drawdown": 0.0, "sma200": 100.0, "vix": 10.0, "is_month_start": True})
    order = strategy.on_day(market_state, state)[0]
    assert order.price == 101.0


def test_cash_behavior_for_monthly_deposit_and_order():
    cfg = BacktestConfig(monthly_contribution=1000.0, min_order_eur=1000.0, slippage=0.0)
    strategy = DollarCostAveragingStrategy(cfg)
    market_df = pd.DataFrame({
        "close": [100.0],
        "drawdown": [0.0],
        "sma200": [100.0],
        "vix": [20.0],
        "is_month_start": [True],
    }, index=pd.to_datetime(["2020-01-02"]))
    engine = BacktestEngine(cfg, strategy, logging.getLogger("test"))
    equity, trades = engine.run(market_df)
    assert len(trades) == 1
    assert equity.iloc[0]["cash_ocf"] == 0.0
    assert equity.iloc[0]["portfolio_value"] == 1000.0


def test_twrr_and_xirr_calculation():
    dates = pd.to_datetime(["2020-01-01", "2021-01-01"])
    equity = pd.Series([1000.0, 1100.0], index=dates)
    cashflows = pd.Series([1000.0, 0.0], index=dates)
    assert abs(calculate_twrr(equity, cashflows) - 0.1) < 1e-8
    xirr_value = calculate_xirr(cashflows, 1100.0)
    assert abs(xirr_value - 0.1) < 0.01
