from typing import Annotated, Dict, List, Optional, Tuple
from datetime import datetime, time
import pandas as pd
import numpy as np

from tradingagents.wallet.manager import WalletManager
from tradingagents.dataflows.vendors.kotak_neo.trading import place_order as kotak_neo_place_order, get_live_price as kotak_neo_get_live_price
from tradingagents.dataflows.vendors.tradingview.technical_indicators import get_technical_indicators
from tradingagents.dataflows.errors import VendorUnavailableError


class IntradayTradingStrategy:
    """Intraday trading strategy using technical analysis and momentum."""

    def __init__(self, wallet_manager: WalletManager = None):
        self.wallet_manager = wallet_manager or WalletManager()
        self.name = "Intraday Momentum Strategy"

        # Intraday trading parameters
        self.market_open = time(9, 15)  # NSE/BSE opens at 9:15 AM
        self.market_close = time(15, 30)  # NSE/BSE closes at 3:30 PM
        self.square_off_time = time(15, 15)  # Square off positions by 3:15 PM

        # Strategy parameters
        self.rsi_overbought = 70
        self.rsi_oversold = 30
        self.macd_signal_threshold = 0
        self.bb_width_threshold = 0.02  # 2% Bollinger Band width
        self.volume_spike_threshold = 2.0  # 2x average volume

    def is_market_open(self) -> bool:
        """Check if the market is currently open."""
        now = datetime.now().time()
        return self.market_open <= now <= self.market_close

    def should_square_off(self) -> bool:
        """Check if it's time to square off positions."""
        now = datetime.now().time()
        return now >= self.square_off_time

    def analyze_stock_for_intraday(self, ticker: str) -> Dict[str, any]:
        """Analyze a stock for intraday trading opportunities.

        Args:
            ticker: Stock ticker symbol (e.g., RELIANCE.NS)

        Returns:
            Dictionary containing analysis results and trading signal
        """
        try:
            # Get live price
            live_price = kotak_neo_get_live_price(ticker)
            if live_price <= 0:
                return {"signal": "HOLD", "confidence": 0, "reason": "Unable to get live price"}

            # Get technical indicators
            indicators = get_technical_indicators(
                ticker=ticker,
                indicators=["RSI", "MACD", "BBANDS", "MOVING_AVERAGES"]
            )

            if not indicators:
                return {"signal": "HOLD", "confidence": 0, "reason": "Unable to get technical indicators"}

            # Extract indicator values
            rsi = indicators.get("RSI", 50)
            macd = indicators.get("MACD", 0)
            macd_signal = indicators.get("MACD_signal", 0)
            macd_hist = indicators.get("MACD_hist", 0)
            bb_upper = indicators.get("BBAND_upper", 0)
            bb_lower = indicators.get("BBAND_lower", 0)
            bb_middle = indicators.get("BBAND_middle", 0)

            # Calculate Bollinger Band width
            bb_width = (bb_upper - bb_lower) / bb_middle if bb_middle > 0 else 0

            # Get moving averages
            ma_5 = indicators.get("MA_5", live_price)
            ma_10 = indicators.get("MA_10", live_price)
            ma_20 = indicators.get("MA_20", live_price)

            # Initialize signal components
            signal_score = 0
            reasons = []

            # RSI signals
            if rsi < self.rsi_oversold:
                signal_score += 2  # Strong buy signal
                reasons.append(f"RSI oversold ({rsi:.1f})")
            elif rsi > self.rsi_overbought:
                signal_score -= 2  # Strong sell signal
                reasons.append(f"RSI overbought ({rsi:.1f})")
            elif rsi < 40:
                signal_score += 1  # Weak buy signal
                reasons.append(f"RSI low ({rsi:.1f})")
            elif rsi > 60:
                signal_score -= 1  # Weak sell signal
                reasons.append(f"RSI high ({rsi:.1f})")

            # MACD signals
            if macd > macd_signal and macd_hist > 0:
                signal_score += 1  # Bullish MACD
                reasons.append("MACD bullish crossover")
            elif macd < macd_signal and macd_hist < 0:
                signal_score -= 1  # Bearish MACD
                reasons.append("MACD bearish crossover")

            # Moving average signals
            if ma_5 > ma_10 > ma_20:
                signal_score += 1  # Bullish MA alignment
                reasons.append("Bullish MA alignment (5>10>20)")
            elif ma_5 < ma_10 < ma_20:
                signal_score -= 1  # Bearish MA alignment
                reasons.append("Bearish MA alignment (5<10<20)")

            # Price position relative to Bollinger Bands
            if live_price < bb_lower:
                signal_score += 1  # Price below lower band - potential bounce
                reasons.append("Price below Bollinger Lower Band")
            elif live_price > bb_upper:
                signal_score -= 1  # Price above upper band - potential pullback
                reasons.append("Price above Bollinger Upper Band")

            # Determine final signal
            if signal_score >= 3:
                signal = "STRONG_BUY"
                confidence = min(90, 50 + signal_score * 8)
            elif signal_score >= 1:
                signal = "BUY"
                confidence = min(70, 50 + signal_score * 6)
            elif signal_score <= -3:
                signal = "STRONG_SELL"
                confidence = min(90, 50 + abs(signal_score) * 8)
            elif signal_score <= -1:
                signal = "SELL"
                confidence = min(70, 50 + abs(signal_score) * 6)
            else:
                signal = "HOLD"
                confidence = 50

            # Calculate suggested entry, stop loss, and target
            if signal in ["BUY", "STRONG_BUY"]:
                entry_price = live_price
                stop_loss = entry_price * 0.98  # 2% stop loss
                target = entry_price * 1.04  # 4% target (2:1 reward:risk)
            elif signal in ["SELL", "STRONG_SELL"]:
                entry_price = live_price
                stop_loss = entry_price * 1.02  # 2% stop loss
                target = entry_price * 0.96  # 4% target (2:1 reward:risk)
            else:
                entry_price = stop_loss = target = 0

            return {
                "signal": signal,
                "confidence": confidence,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "target": target,
                "signal_score": signal_score,
                "reasons": reasons,
                "indicators": indicators,
                "live_price": live_price,
                "timestamp": datetime.now().isoformat()
            }

        except VendorUnavailableError as e:
            return {"signal": "HOLD", "confidence": 0, "reason": f"Vendor unavailable: {str(e)}"}
        except Exception as e:
            return {"signal": "HOLD", "confidence": 0, "reason": f"Analysis error: {str(e)}"}

    def execute_intraday_trade(self, ticker: str, capital_allocation: float = 0.1) -> Dict[str, any]:
        """Execute an intraday trade based on strategy analysis.

        Args:
            ticker: Stock ticker symbol
            capital_allocation: Fraction of available capital to use (0.1 = 10%)

        Returns:
            Dictionary containing trade execution results
        """
        if not self.is_market_open():
            return {"success": False, "reason": "Market is closed"}

        if self.should_square_off():
            return {"success": False, "reason": "Time to square off positions"}

        # Analyze the stock
        analysis = self.analyze_stock_for_intraday(ticker)

        if analysis["signal"] in ["HOLD"] or analysis["confidence"] < 50:
            return {
                "success": False,
                "reason": f"No clear signal: {analysis.get('reason', 'Insufficient confidence')}",
                "analysis": analysis
            }

        # Calculate position size
        available_capital = self.wallet_manager.get_available_capital()
        trade_capital = available_capital * capital_allocation

        entry_price = analysis["entry_price"]
        stop_loss = analysis["stop_loss"]

        if entry_price <= 0:
            return {"success": False, "reason": "Invalid entry price", "analysis": analysis}

        # Calculate quantity based on risk management
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share <= 0:
            return {"success": False, "reason": "Invalid risk calculation", "analysis": analysis}

        max_risk_amount = self.wallet_manager.get_total_portfolio_value() * self.wallet_manager.config.risk_per_trade
        quantity_by_risk = int(max_risk_amount / risk_per_share)
        quantity_by_capital = int(trade_capital / entry_price)
        quantity = min(quantity_by_risk, quantity_by_capital)

        if quantity <= 0:
            return {"success": False, "reason": "Insufficient capital for trade", "analysis": analysis}

        # Determine action based on signal
        if analysis["signal"] in ["BUY", "STRONG_BUY"]:
            action = "BUY"
        elif analysis["signal"] in ["SELL", "STRONG_SELL"]:
            action = "SELL"
        else:
            return {"success": False, "reason": "Invalid signal for execution", "analysis": analysis}

        # Place the order
        try:
            order_result = self.wallet_manager.place_order_via_broker(
                ticker=ticker,
                action=action,
                quantity=quantity,
                order_type="MARKET",
                price=None,
                product_type="MIS"  # Intraday order
            )

            # Record the trade
            trade_record = {
                "trade_id": f"INTRA_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "ticker": ticker,
                "action": action,
                "quantity": quantity,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "target": analysis["target"],
                "order_id": order_result.get("order_id"),
                "timestamp": datetime.now().isoformat(),
                "strategy": self.name,
                "analysis": analysis
            }

            self.wallet_manager.transaction_history.append(trade_record)

            return {
                "success": True,
                "trade_record": trade_record,
                "order_result": order_result,
                "analysis": analysis
            }

        except VendorUnavailableError as e:
            return {"success": False, "reason": f"Broker unavailable: {str(e)}", "analysis": analysis}
        except Exception as e:
            return {"success": False, "reason": f"Order execution failed: {str(e)}", "analysis": analysis}

    def square_off_all_positions(self) -> Dict[str, any]:
        """Square off all open intraday positions."""
        if not self.is_market_open():
            return {"success": False, "reason": "Market is closed"}

        try:
            # Get current positions
            portfolio = self.wallet_manager.get_portfolio_summary()
            positions = portfolio.get("positions", [])

            squared_off = []
            failed = []

            for position in positions:
                ticker = position["ticker"]
                quantity = position["quantity"]

                # Determine opposite action to close position
                action = "SELL" if position["quantity"] > 0 else "BUY"
                close_quantity = abs(position["quantity"])

                # Get live price for closing
                try:
                    live_price = kotak_neo_get_live_price(ticker)
                    if live_price <= 0:
                        failed.append({"ticker": ticker, "reason": "Unable to get live price"})
                        continue
                except VendorUnavailableError:
                    failed.append({"ticker": ticker, "reason": "Unable to get live price"})
                    continue

                # Place market order to close position
                try:
                    order_result = self.wallet_manager.place_order_via_broker(
                        ticker=ticker,
                        action=action,
                        quantity=close_quantity,
                        order_type="MARKET",
                        price=None,
                        product_type="MIS"
                    )

                    squared_off.append({
                        "ticker": ticker,
                        "quantity": close_quantity,
                        "action": action,
                        "order_id": order_result.get("order_id"),
                        "price": live_price
                    })

                except Exception as e:
                    failed.append({"ticker": ticker, "reason": str(e)})

            return {
                "success": len(failed) == 0,
                "squared_off": squared_off,
                "failed": failed,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            return {"success": False, "reason": f"Square off failed: {str(e)}"}


# Global intraday strategy instance
intraday_strategy = IntradayTradingStrategy()