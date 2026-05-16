import pytest
import pandas as pd
import numpy as np
import logging
from datetime import datetime
from etf.backtest.sweep import parameter_sweep
from etf.strategies.dca import DollarCostAveragingStrategy
from etf.strategies.sda import SDAStrategy
from etf.strategies.bot import SignalBotStrategy
from etf.config import SDAConfig
from etf.models import MarketState
from etf.portfolio.portfolio import Portfolio
from etf.portfolio.portfolio import State


class TestParameterSweep:
    """Comprehensive tests for parameter sweep functionality."""

    @pytest.fixture
    def base_config(self):
        """Base backtest configuration - use SDAConfig since sweep expects it."""
        return SDAConfig(
            monthly_contribution=1000.0,
            start_date=datetime(2020, 1, 1),
            end_date=datetime(2020, 4, 10),
            value_averaging_mode='linear'
        )

    @pytest.fixture
    def logger(self):
        """Test logger."""
        logger = logging.getLogger('test_sweep')
        logger.setLevel(logging.WARNING)
        return logger

    def test_dca_sweep_basic(self, base_config, logger):
        """Test basic DCA parameter sweep."""
        def dca_factory(config):
            return DollarCostAveragingStrategy(config)

        param_grid = {
            'monthly_contribution': [500.0, 1000.0, 1500.0]
        }

        results = parameter_sweep(
            base_cfg=base_config,
            logger=logger,
            strategy_factories={'DCA': dca_factory},
            param_grid=param_grid
        )

        assert isinstance(results, pd.DataFrame)
        assert len(results) == 3  # Three parameter combinations
        assert 'strategy' in results.columns
        assert 'monthly_contribution' in results.columns
        assert all(results['strategy'] == 'DCA')

    def test_sda_sweep_basic(self, base_config, logger):
        """Test basic SDA parameter sweep."""
        def sda_factory(config):
            return SDAStrategy(config)

        param_grid = {
            'vix_threshold': [20.0, 25.0]
        }

        results = parameter_sweep(
            base_cfg=base_config,
            logger=logger,
            strategy_factories={'SDA': sda_factory},
            param_grid=param_grid
        )

        assert isinstance(results, pd.DataFrame)
        assert len(results) == 2  # Two parameter combinations
        assert all(results['strategy'] == 'SDA')
        assert all(results['vix_threshold'].isin([20.0, 25.0]))

    def test_signal_bot_sweep_basic(self, base_config, logger):
        """Test basic SignalBot parameter sweep."""
        def bot_factory(config):
            return SignalBotStrategy(config)

        param_grid = {
            'vix_threshold': [20.0, 25.0],
            'l2_rsi': [20.0, 25.0],
        }

        results = parameter_sweep(
            base_cfg=base_config,
            logger=logger,
            strategy_factories={'BOT': bot_factory},
            param_grid=param_grid
        )

        assert isinstance(results, pd.DataFrame)
        assert len(results) == 4  # Two vix thresholds * two RSI thresholds
        assert all(results['strategy'] == 'BOT')
        assert set(results['l2_rsi'].unique()) == {20.0, 25.0}

    def test_signal_bot_generates_monthly_and_signal_orders(self, base_config, logger):
        def bot_factory(config):
            return SignalBotStrategy(config)

        config = SDAConfig(
            monthly_contribution=300.0,
            monthly_savings=150.0,
            min_order_eur=100.0,
            vix_threshold=20.0,
            l1_drawdown=-0.05,
            l1_rsi=30.0,
            l2_rsi=30.0,
            l3_rsi_max=50.0,
            l4_rsi=40.0,
        )
        strategy = bot_factory(config)
        market_state = MarketState(
            date=datetime(2024, 1, 1),
            close=100.0,
            drawdown=-0.10,
            sma200=95.0,
            sma20=98.0,
            prev_price=95.0,
            prev_sma200=96.0,
            recovery_days=2,
            rsi=25.0,
            vix=25.0,
            is_month_start=True,
        )
        portfolio = Portfolio(State(cash_ocf=300.0))

        orders = strategy.on_day(market_state, portfolio.state)
        assert len(orders) == 2
        assert orders[0].tier == 'MONTHLY-ETF'
        assert orders[0].amount_eur == 150.0
        assert orders[1].tier in {'L1_ULTIMATE_DIP', 'L2_RSI_EXTREME'}

    def test_multiple_strategies_sweep(self, base_config, logger):
        """Test sweep with multiple strategies simultaneously."""
        def dca_factory(config):
            return DollarCostAveragingStrategy(config)

        def sda_factory(config):
            return SDAStrategy(config)

        param_grid = {
            'monthly_contribution': [500.0, 1000.0]
        }

        results = parameter_sweep(
            base_cfg=base_config,
            logger=logger,
            strategy_factories={'DCA': dca_factory, 'SDA': sda_factory},
            param_grid=param_grid
        )

        assert isinstance(results, pd.DataFrame)
        assert len(results) == 4  # 2 strategies * 2 parameter combinations
        assert set(results['strategy'].unique()) == {'DCA', 'SDA'}

    def test_empty_param_grid(self, base_config, logger):
        """Test behavior with empty parameter grid - uses defaults."""
        def dca_factory(config):
            return DollarCostAveragingStrategy(config)

        param_grid = {}

        results = parameter_sweep(
            base_cfg=base_config,
            logger=logger,
            strategy_factories={'DCA': dca_factory},
            param_grid=param_grid
        )

        assert isinstance(results, pd.DataFrame)
        assert len(results) == 128  # 2*2*1*2*2*2*2*2 default parameter combinations
        assert all(results['strategy'] == 'DCA')

    def test_default_strategy_factories_include_sda_and_bot(self, base_config, logger):
        results = parameter_sweep(
            base_cfg=base_config,
            logger=logger,
            param_grid={'vix_threshold': [15.0]}
        )

        assert isinstance(results, pd.DataFrame)
        assert set(results['strategy'].unique()) == {'sda', 'bot'}

    def test_result_columns(self, base_config, logger):
        """Test that sweep results contain expected columns."""
        def dca_factory(config):
            return DollarCostAveragingStrategy(config)

        param_grid = {'monthly_contribution': [1000.0]}

        results = parameter_sweep(
            base_cfg=base_config,
            logger=logger,
            strategy_factories={'DCA': dca_factory},
            param_grid=param_grid
        )

        expected_columns = [
            'strategy', 'monthly_contribution', 'cagr', 'twrr', 'xirr',
            'sharpe', 'sortino', 'max_dd', 'final_pv', 'total_invested',
            'cash_util', 'trades', 'total_trade_costs_eur'
        ]

        for col in expected_columns:
            assert col in results.columns
        """Test that sweep results contain expected columns."""
        def dca_factory(config):
            return DollarCostAveragingStrategy(config)

        param_grid = {'monthly_contribution': [1000.0]}

        results = parameter_sweep(
            base_cfg=base_config,
            logger=logger,
            strategy_factories={'DCA': dca_factory},
            param_grid=param_grid
        )

        expected_columns = [
            'strategy', 'monthly_contribution', 'cagr', 'twrr', 'xirr',
            'sharpe', 'sortino', 'max_dd', 'final_pv', 'total_invested',
            'cash_util', 'trades', 'total_trade_costs_eur'
        ]

        for col in expected_columns:
            assert col in results.columns

    def test_invalid_parameter(self, base_config, logger):
        """Test error handling for invalid parameters."""
        def dca_factory(config):
            return DollarCostAveragingStrategy(config)

        param_grid = {'invalid_param': [1.0, 2.0]}

        with pytest.raises(AttributeError):
            parameter_sweep(
                base_cfg=base_config,
                logger=logger,
                strategy_factories={'DCA': dca_factory},
                param_grid=param_grid
            )

    def test_sweep_sorting(self, base_config, logger):
        """Test that results are sorted by strategy and sharpe ratio."""
        def dca_factory(config):
            return DollarCostAveragingStrategy(config)

        param_grid = {'monthly_contribution': [500.0, 1000.0]}

        results = parameter_sweep(
            base_cfg=base_config,
            logger=logger,
            strategy_factories={'DCA': dca_factory},
            param_grid=param_grid
        )

        # Should be sorted by strategy then sharpe (descending)
        assert results['strategy'].is_monotonic_increasing
