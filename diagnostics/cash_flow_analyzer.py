"""
Cash Flow Analyzer - Diagnostic tool for ETF backtesting cash management issues

This tool reproduces and analyzes the "Insufficient cash for order" error
that occurs during parameter sweeps, particularly with vix_threshold=20.0.
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Any
from dataclasses import dataclass

from etf.config import SDAConfig
from etf.strategies.sda import SDAStrategy
from etf.backtest.engine import BacktestEngine
from etf.models import Order, State, MarketState
from etf.data.loader import load_etf_data


@dataclass
class CashFlowEvent:
    """Represents a cash flow event for analysis."""
    date: datetime
    event_type: str  # 'deposit', 'order_attempt', 'order_success', 'order_failure'
    amount: float
    cash_before: float
    cash_after: float
    order_details: Dict[str, Any] = None
    error_message: str = None


class CashFlowAnalyzer:
    """Analyzes cash flow during backtesting to identify cash constraint issues."""

    def __init__(self, config: SDAConfig):
        self.config = config
        self.events: List[CashFlowEvent] = []
        self.logger = logging.getLogger('CashFlowAnalyzer')

        # Set up logging
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    def analyze_failing_combination(self) -> Dict[str, Any]:
        """
        Reproduce the exact failing combination (vix_threshold=20.0) and analyze cash flow.
        """
        self.logger.info("=== Starting Cash Flow Analysis ===")
        self.logger.info(f"Configuration: vix_threshold={self.config.vix_threshold}")

        # Load data
        logger = logging.getLogger('ETF')
        logger.setLevel(logging.WARNING)  # Reduce noise

        try:
            etf_data, vix_data = load_etf_data(self.config, logger)
            self.logger.info(f"Loaded data: {len(etf_data)} ETF records, {len(vix_data)} VIX records")
        except Exception as e:
            self.logger.error(f"Failed to load data: {e}")
            return {"error": f"Data loading failed: {e}"}

        # Create strategy and engine
        strategy = SDAStrategy(self.config)

        # Create a custom engine that logs cash flow
        engine = CashFlowLoggingEngine(self.config, strategy, self)

        try:
            self.logger.info("Starting backtest execution...")
            equity, trades = engine.run()
            self.logger.info("Backtest completed successfully")
            return {
                "success": True,
                "events": self.events,
                "final_equity": equity.iloc[-1] if not equity.empty else 0,
                "total_trades": len(trades)
            }
        except ValueError as e:
            if "Insufficient cash" in str(e):
                self.logger.error(f"Cash error occurred: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "events": self.events,
                    "failing_event": self.events[-1] if self.events else None
                }
            else:
                raise

    def log_cash_event(self, event: CashFlowEvent):
        """Log a cash flow event."""
        self.events.append(event)

        if event.event_type == 'order_failure':
            self.logger.error(f"CASH ERROR: {event.error_message}")
            self.logger.error(f"  Date: {event.date}")
            self.logger.error(f"  Cash before: €{event.cash_before:.2f}")
            self.logger.error(f"  Order amount: €{event.amount:.2f}")
            self.logger.error(f"  Order details: {event.order_details}")
        elif event.event_type == 'order_attempt':
            self.logger.info(f"Order attempt: €{event.amount:.2f}, Cash: €{event.cash_before:.2f}")
        elif event.event_type == 'deposit':
            self.logger.info(f"Cash deposit: €{event.amount:.2f}, New total: €{event.cash_after:.2f}")

    def calculate_max_affordable_order(self, cash: float, price: float, slippage: float = 0.0005) -> Dict[str, Any]:
        """Calculate the maximum affordable order given current cash and price."""
        # Account for slippage
        effective_price = price * (1 + slippage)

        # Maximum shares we can afford
        max_shares = cash / effective_price

        # Round down to whole shares
        max_shares_whole = int(max_shares)

        # Maximum amount
        max_amount = max_shares_whole * effective_price

        return {
            "max_shares": max_shares,
            "max_shares_whole": max_shares_whole,
            "max_amount": max_amount,
            "effective_price": effective_price,
            "cash_utilization": max_amount / cash if cash > 0 else 0
        }

    def analyze_events(self) -> Dict[str, Any]:
        """Analyze the collected cash flow events."""
        if not self.events:
            return {"error": "No events to analyze"}

        deposits = [e for e in self.events if e.event_type == 'deposit']
        order_attempts = [e for e in self.events if e.event_type in ['order_attempt', 'order_success']]
        failures = [e for e in self.events if e.event_type == 'order_failure']

        total_deposited = sum(e.amount for e in deposits)
        total_attempted = sum(e.amount for e in order_attempts)

        return {
            "total_events": len(self.events),
            "deposits": len(deposits),
            "order_attempts": len(order_attempts),
            "failures": len(failures),
            "total_deposited": total_deposited,
            "total_attempted": total_attempted,
            "success_rate": len(order_attempts) / max(1, len(order_attempts) + len(failures)),
            "failing_events": failures
        }


class CashFlowLoggingEngine(BacktestEngine):
    """Extended BacktestEngine that logs cash flow events."""

    def __init__(self, cfg, strategy, analyzer: CashFlowAnalyzer):
        super().__init__(cfg, strategy, logging.getLogger('CashFlowEngine'))
        self.analyzer = analyzer

    def run(self):
        """Override run to add cash flow logging."""
        # Initialize market state
        self.market_state = MarketState(
            date=self.cfg.start_date,
            close=0.0,
            drawdown=0.0,
            vix=0.0,
            sma200=0.0,
            is_month_start=False
        )

        # Load data
        etf_data, vix_data = load_etf_data(self.cfg, self.logger)

        # Initialize portfolio
        self.portfolio = CashFlowLoggingPortfolio(self.cfg, self.analyzer)

        equity_curve = []
        trades = []

        # Main simulation loop
        current_date = pd.to_datetime(self.cfg.start_date)
        end_date = pd.to_datetime(self.cfg.end_date)
        while current_date <= end_date:
            if current_date in etf_data.index:
                # Update market state
                etf_row = etf_data.loc[current_date]
                vix_value = vix_data.loc[current_date] if current_date in vix_data.index else np.nan

                self.market_state = MarketState(
                    date=current_date,
                    close=etf_row['close'],  # Changed from 'Close' to 'close'
                    drawdown=etf_row.get('drawdown', 0.0),
                    vix=vix_value,
                    sma200=etf_row.get('SMA200', etf_row['close']),  # Changed from 'Close' to 'close'
                    is_month_start=current_date.day == 1
                )

                # Apply monthly contribution
                if self.market_state.is_month_start:
                    self.portfolio.add_cash(self.cfg.monthly_contribution)

                # Get orders from strategy
                orders = self.strategy.on_day(self.market_state, self.portfolio.state)

                # Execute orders
                for order in orders:
                    try:
                        trade = self.portfolio.execute_order(order)
                        if trade:
                            trades.append(trade)
                    except ValueError as e:
                        if "Insufficient cash" in str(e):
                            # Log the failure but don't crash
                            self.analyzer.log_cash_event(CashFlowEvent(
                                date=current_date,
                                event_type='order_failure',
                                amount=order.amount_eur,
                                cash_before=self.portfolio.state.cash_ocf,
                                cash_after=self.portfolio.state.cash_ocf,
                                order_details={
                                    'tier': order.tier,
                                    'price': order.price,
                                    'units': order.units,
                                    'drawdown': order.drawdown,
                                    'vix': order.vix
                                },
                                error_message=str(e)
                            ))
                            raise  # Re-raise to maintain original behavior
                        else:
                            raise

                # Update portfolio value
                self.portfolio.update_portfolio_value(self.market_state.close)

                # Record equity
                equity_curve.append({
                    'date': current_date,
                    'equity': self.portfolio.state.portfolio_value
                })

            # Move to next day
            current_date += pd.Timedelta(days=1)

        return pd.DataFrame(equity_curve).set_index('date'), trades


class CashFlowLoggingPortfolio:
    """Extended Portfolio that logs cash flow events."""

    def __init__(self, cfg, analyzer: CashFlowAnalyzer):
        from etf.models import State
        from etf.portfolio.portfolio import Portfolio
        self.portfolio = Portfolio(State(cash_ocf=cfg.initial_cash))
        self.analyzer = analyzer

    @property
    def state(self):
        return self.portfolio.state

    def add_cash(self, amount: float):
        """Add cash with logging."""
        cash_before = self.state.cash_ocf
        self.portfolio.add_cash(amount)
        cash_after = self.state.cash_ocf

        self.analyzer.log_cash_event(CashFlowEvent(
            date=self.state.current_date if hasattr(self.state, 'current_date') else datetime.now(),
            event_type='deposit',
            amount=amount,
            cash_before=cash_before,
            cash_after=cash_after
        ))

    def execute_order(self, order: Order):
        """Execute order with cash flow logging."""
        cash_before = self.state.cash_ocf

        # Log the attempt
        self.analyzer.log_cash_event(CashFlowEvent(
            date=order.date,
            event_type='order_attempt',
            amount=order.amount_eur,
            cash_before=cash_before,
            cash_after=cash_before,  # Will be updated if successful
            order_details={
                'tier': order.tier,
                'price': order.price,
                'units': order.units
            }
        ))

        # Execute the order
        trade = self.portfolio.execute_order(order)

        if trade:
            cash_after = self.state.cash_ocf
            # Update the last event with success
            if self.analyzer.events and self.analyzer.events[-1].event_type == 'order_attempt':
                self.analyzer.events[-1].event_type = 'order_success'
                self.analyzer.events[-1].cash_after = cash_after

    def update_portfolio_value(self, price: float) -> None:
        """Update portfolio value."""
        self.portfolio.update_portfolio_value(price)


def main():
    """Main diagnostic function."""
    # Create the failing configuration
    config = SDAConfig(
        monthly_contribution=500.0,
        vix_threshold=20.0,  # This is the failing combination
        ocf_target=3000.0
    )

    analyzer = CashFlowAnalyzer(config)
    result = analyzer.analyze_failing_combination()

    print("\n=== ANALYSIS RESULTS ===")
    if result.get("success"):
        print("✅ Backtest completed successfully")
    else:
        print("❌ Cash error occurred")
        print(f"Error: {result.get('error')}")

        failing_event = result.get('failing_event')
        if failing_event:
            print(f"Failing event: {failing_event}")

    # Analyze events
    analysis = analyzer.analyze_events()
    print(f"\nEvents summary: {analysis}")

    # Calculate what the max affordable order would be
    if analyzer.events:
        last_event = analyzer.events[-1]
        if hasattr(analyzer, 'calculate_max_affordable_order'):
            max_order = analyzer.calculate_max_affordable_order(
                last_event.cash_before,
                last_event.order_details.get('price', 100) if last_event.order_details else 100
            )
            print(f"\nMax affordable order analysis: {max_order}")

    return result


if __name__ == "__main__":
    main()