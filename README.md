# ETF Backtest Framework

A modular, quantitative backtesting framework for ETF strategies, featuring the Systematic Drawdown Accumulator (SDA) approach.

## Features

- **Modular Architecture**: Clean separation of data loading, strategy logic, portfolio management, analytics, and backtesting engine.
- **SDA Strategy**: Path-dependent cashflow state machine with dip-buy tiers and opportunity cost reserves.
- **Parameter Sweeps**: Automated grid search over strategy parameters.
- **Comprehensive Analytics**: CAGR, Sharpe ratio, drawdown analysis, and equity curve plotting.
- **CLI Interface**: Easy command-line execution with optional parameter sweeps.

## Installation

```bash
pip install -e .
```

## Usage

### Basic Backtest

```bash
python -m etf.cli.main
```

### With Parameter Sweep

```bash
python -m etf.cli.main --sweep
```

## Configuration

Edit `etf/config.py` or pass configuration via CLI (future feature).

## Architecture

- `data/`: Data loading and indicator computation
- `strategies/`: Trading strategy implementations
- `portfolio/`: Portfolio state and order execution
- `analytics/`: Performance metrics and reporting
- `backtest/`: Simulation engine and parameter sweeps
- `cli/`: Command-line interface

## Extending

Implement new strategies by inheriting from `etf.strategies.base.Strategy` and overriding `on_day()`.

## License

MIT