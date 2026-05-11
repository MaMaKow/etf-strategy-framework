import pytest
import pandas as pd
import numpy as np
import logging
from datetime import datetime
from etf.backtest.sweep import parameter_sweep
from etf.strategies.dca import DollarCostAveragingStrategy
from etf.strategies.sda import SDAStrategy
from etf.config import SDAConfig


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
        assert len(results) == 168  # 7*6*4*1 default parameter combinations
        assert all(results['strategy'] == 'DCA')

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
            'cash_util', 'trades'
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
            'cash_util', 'trades'
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