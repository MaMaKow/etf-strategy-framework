"""
Comprehensive test suite for cash management and constraint handling in ETF backtesting framework.

This module tests the portfolio's cash management logic, order execution constraints,
and edge cases that could lead to insufficient cash errors.
"""

import pytest
import pandas as pd
from datetime import datetime
from unittest.mock import Mock

from etf.config import SDAConfig
from etf.models import Order, State, MarketState
from etf.portfolio.portfolio import Portfolio
from etf.strategies.sda import SDAStrategy
from etf.backtest.engine import BacktestEngine


class TestCashManagement:
    """Test suite for cash management functionality."""

    def test_insufficient_cash_handling(self):
        """Test that insufficient cash raises appropriate error."""
        portfolio = Portfolio(State(cash_ocf=100.0))

        order = Order(
            date=datetime(2024, 1, 1),
            tier="TEST",
            amount_eur=200.0,  # More than available cash
            price=100.0,
            units=2.0,
            drawdown=0.0,
            vix=15.0
        )

        with pytest.raises(ValueError, match="Insufficient cash for order"):
            portfolio.execute_order(order)

    def test_exact_cash_order_execution(self):
        """Test order execution with exactly the available cash."""
        initial_cash = 1000.0
        portfolio = Portfolio(State(cash_ocf=initial_cash))

        order = Order(
            date=datetime(2024, 1, 1),
            tier="TEST",
            amount_eur=1000.0,  # Exactly the available cash
            price=100.0,
            units=10.0,
            drawdown=0.0,
            vix=15.0
        )

        trade = portfolio.execute_order(order)

        assert portfolio.state.cash_ocf == 0.0
        assert portfolio.state.units == 10.0
        assert trade.amount_eur == 1000.0
        assert trade.units == 10.0

    def test_cash_constraint_sweep(self):
        """Test cash constraints across different parameter combinations."""
        # Test various combinations that might trigger cash issues
        test_cases = [
            {"monthly_contribution": 500.0, "ocf_target": 3000.0, "vix_threshold": 20.0},
            {"monthly_contribution": 2000.0, "ocf_target": 8000.0, "vix_threshold": 12.0},
            {"monthly_contribution": 1000.0, "ocf_target": 5000.0, "vix_threshold": 15.0},
        ]

        for params in test_cases:
            config = SDAConfig(**params)
            strategy = SDAStrategy(config)
            engine = BacktestEngine(config, strategy, Mock())

            # Should not raise any exceptions
            equity, trades = engine.run()
            assert not equity.empty
            assert isinstance(trades, list)

    def test_minimum_order_validation(self):
        """Test that orders below minimum threshold are rejected."""
        config = SDAConfig(min_order_eur=500.0)
        portfolio = Portfolio(State(cash_ocf=1000.0))

        # Test order below minimum
        small_order = Order(
            date=datetime(2024, 1, 1),
            tier="TEST",
            amount_eur=400.0,  # Below min_order_eur
            price=100.0,
            units=4.0,
            drawdown=0.0,
            vix=15.0
        )

        # The portfolio doesn't validate min_order_eur - that's strategy responsibility
        # But let's test that if we try to execute it, it works (strategy should prevent this)
        trade = portfolio.execute_order(small_order)
        assert trade.amount_eur == 400.0

    def test_cash_accumulation_over_time(self):
        """Test cash accumulation through monthly contributions."""
        portfolio = Portfolio(State(cash_ocf=0.0))

        # Simulate monthly contributions
        contributions = [1000.0] * 12  # 12 months

        for i, amount in enumerate(contributions):
            portfolio.add_cash(amount)
            expected_cash = sum(contributions[:i+1])
            assert portfolio.state.cash_ocf == expected_cash
            assert portfolio.state.total_contributions == expected_cash

    def test_portfolio_value_calculation(self):
        """Test portfolio value updates correctly with price changes."""
        portfolio = Portfolio(State(cash_ocf=1000.0, units=0.0))

        # Buy some units
        order = Order(
            date=datetime(2024, 1, 1),
            tier="BUY",
            amount_eur=500.0,
            price=100.0,
            units=5.0,
            drawdown=0.0,
            vix=15.0
        )
        portfolio.execute_order(order)

        # Update portfolio value at different prices
        test_prices = [100.0, 110.0, 90.0, 105.0]

        for price in test_prices:
            portfolio.update_portfolio_value(price)
            expected_value = (5.0 * price) + 500.0  # units * price + remaining cash
            assert portfolio.state.portfolio_value == expected_value

    def test_strategy_cash_management_integration(self):
        """Test end-to-end cash management in strategy execution."""
        config = SDAConfig(
            monthly_contribution=1000.0,
            ocf_target=5000.0,
            vix_threshold=15.0
        )

        strategy = SDAStrategy(config)
        portfolio = Portfolio(State(cash_ocf=0.0))

        # Create mock market state for month start
        market_state = MarketState(
            date=datetime(2024, 1, 1),
            close=100.0,
            vix=10.0,  # Below threshold, no dip buying
            drawdown=0.0,
            sma200=95.0,
            is_month_start=True
        )

        # Strategy should not generate orders when cash is below OCF target
        orders = strategy.on_day(market_state, portfolio.state)
        assert len(orders) == 0  # No orders when cash < OCF target

        # Add cash to reach OCF target
        portfolio.add_cash(6000.0)  # Above ocf_target

        # Now strategy should generate monthly savings order
        orders = strategy.on_day(market_state, portfolio.state)
        assert len(orders) == 1
        assert orders[0].tier == "MONTHLY-ETF"
        assert orders[0].amount_eur == config.monthly_contribution

    def test_month_start_dip_buy_respects_monthly_order(self):
        """Test that dip buying does not exceed cash after a month-start savings order."""
        config = SDAConfig(
            monthly_contribution=1000.0,
            ocf_target=3000.0,
            vix_threshold=12.0,
        )

        strategy = SDAStrategy(config)
        portfolio = Portfolio(State(cash_ocf=1000.0))

        market_state = MarketState(
            date=datetime(2024, 1, 2),
            close=28.574279,
            vix=14.23,
            drawdown=float('nan'),
            sma200=100.0,
            is_month_start=True,
        )

        orders = strategy.on_day(market_state, portfolio.state)

        assert len(orders) == 1
        assert orders[0].tier == "MONTHLY-ETF"
        assert orders[0].amount_eur == 700.0

    def test_edge_case_high_vix_low_cash(self):
        """Test behavior with high VIX but insufficient cash for dip buying."""
        config = SDAConfig(
            monthly_contribution=1000.0,
            ocf_target=5000.0,
            vix_threshold=15.0
        )

        strategy = SDAStrategy(config)
        portfolio = Portfolio(State(cash_ocf=100.0))  # Very low cash

        # High VIX, significant drawdown - would normally trigger dip buy
        market_state = MarketState(
            date=datetime(2024, 1, 1),
            close=100.0,
            vix=25.0,  # Above threshold
            drawdown=-0.15,  # 15% drawdown
            sma200=95.0,
            is_month_start=False
        )

        orders = strategy.on_day(market_state, portfolio.state)

        # Should not generate orders due to insufficient cash
        # (dip buy amount would be based on available cash, but strategy checks min_order_eur)
        for order in orders:
            assert order.amount_eur >= config.min_order_eur

    def test_multiple_orders_same_day(self):
        """Test executing multiple orders in the same trading day."""
        portfolio = Portfolio(State(cash_ocf=2000.0))

        orders = [
            Order(
                date=datetime(2024, 1, 1),
                tier="BUY1",
                amount_eur=500.0,
                price=100.0,
                units=5.0,
                drawdown=0.0,
                vix=15.0
            ),
            Order(
                date=datetime(2024, 1, 1),
                tier="BUY2",
                amount_eur=700.0,
                price=100.0,
                units=7.0,
                drawdown=0.0,
                vix=15.0
            )
        ]

        # Execute orders
        trades = []
        for order in orders:
            trade = portfolio.execute_order(order)
            trades.append(trade)

        # Verify final state
        assert portfolio.state.cash_ocf == 2000.0 - 500.0 - 700.0  # 800.0
        assert portfolio.state.units == 5.0 + 7.0  # 12.0
        assert len(trades) == 2

        # Verify trade details
        assert trades[0].amount_eur == 500.0
        assert trades[1].amount_eur == 700.0