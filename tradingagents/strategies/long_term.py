from typing import Annotated, Dict, List, Optional
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from tradingagents.wallet.manager import WalletManager
from tradingagents.dataflows.vendors.kotak_neo.trading import (
    place_order as kotak_neo_place_order,
    get_live_price as kotak_neo_get_live_price,
)
from tradingagents.dataflows.vendors.screener_in.fundamentals import (
    get_fundamentals as screener_get_fundamentals,
)
from tradingagents.dataflows.vendors.moneycontrol.fundamentals import (
    get_fundamentals as moneycontrol_get_fundamentals,
)
from tradingagents.dataflows.vendors.tradingview.technical_indicators import (
    get_technical_indicators,
)
from tradingagents.dataflows.errors import VendorUnavailableError


class LongTermInvestmentStrategy:
    """Long-term investment strategy using fundamental analysis and value investing principles."""

    def __init__(self, wallet_manager: WalletManager = None):
        self.wallet_manager = wallet_manager or WalletManager()
        self.name = "Long-Term Value Investing Strategy"

        # Fundamental analysis thresholds
        self.pe_ratio_threshold = 25  # Maximum acceptable P/E ratio
        self.pb_ratio_threshold = 5  # Maximum acceptable P/B ratio
        self.debt_to_equity_threshold = 0.5  # Maximum acceptable debt-to-equity
        self.roe_threshold = 0.15  # Minimum acceptable ROE (15%)
        self.current_ratio_threshold = 1.5  # Minimum acceptable current ratio
        self.dividend_yield_threshold = 0.02  # Minimum acceptable dividend yield (2%)

        # Technical analysis thresholds for entry timing
        self.rsi_oversold = 35
        self.rsi_overbought = 65
        self.ma_consecutive_days = 3  # Days MA should be bullish

        # Diversification limits
        self.max_sector_allocation = 0.25  # Maximum 25% in any sector
        self.max_stock_allocation = 0.10  # Maximum 10% in any single stock

    def analyze_stock_for_long_term(self, ticker: str) -> Dict[str, any]:
        """Analyze a stock for long-term investment potential.

        Args:
            ticker: Stock ticker symbol (e.g., RELIANCE.NS)

        Returns:
            Dictionary containing analysis results and investment signal
        """
        try:
            # Get fundamental data from multiple sources for validation
            fundamentals_screener = None
            fundamentals_moneycontrol = None

            try:
                fundamentals_screener = screener_get_fundamentals(ticker)
            except VendorUnavailableError:
                pass  # Try other source

            try:
                fundamentals_moneycontrol = moneycontrol_get_fundamentals(ticker)
            except VendorUnavailableError:
                pass  # Try other source

            # Use whichever source succeeded, or combine if both worked
            fundamentals = fundamentals_screener or fundamentals_moneycontrol or {}

            if not fundamentals:
                return {
                    "signal": "HOLD",
                    "confidence": 0,
                    "reason": "Unable to get fundamental data",
                }

            # Get live price
            live_price = kotak_neo_get_live_price(ticker)
            if live_price <= 0:
                return {"signal": "HOLD", "confidence": 0, "reason": "Unable to get live price"}

            # Get technical indicators for timing
            indicators = get_technical_indicators(
                ticker=ticker, indicators=["RSI", "MOVING_AVERAGES"]
            )

            # Extract fundamental metrics
            pe_ratio = fundamentals.get("pe_ratio", fundamentals.get("pe", 0))
            pb_ratio = fundamentals.get("pb_ratio", fundamentals.get("pb", 0))
            debt_to_equity = fundamentals.get(
                "debt_to_equity", fundamentals.get("debt_equity_ratio", 0)
            )
            roe = fundamentals.get("roe", fundamentals.get("return_on_equity", 0))
            current_ratio = fundamentals.get("current_ratio", 0)
            dividend_yield = (
                fundamentals.get("dividend_yield", fundamentals.get("dividend_yield_percent", 0))
                / 100
            )  # Convert percentage to decimal
            market_cap = fundamentals.get("market_cap", 0)
            book_value = fundamentals.get("book_value_per_share", 0)

            # Convert percentages if needed
            if roe > 1:  # If ROE is in percentage
                roe = roe / 100
            if dividend_yield > 1:  # If dividend yield is in percentage
                dividend_yield = dividend_yield / 100

            # Initialize scoring
            fundamental_score = 0
            technical_score = 0
            reasons = []

            # Fundamental analysis scoring
            # P/E Ratio
            if pe_ratio > 0:
                if pe_ratio < 15:
                    fundamental_score += 2  # Excellent valuation
                    reasons.append(f"Attractive P/E ratio ({pe_ratio:.1f})")
                elif pe_ratio < self.pe_ratio_threshold:
                    fundamental_score += 1  # Acceptable valuation
                    reasons.append(f"Reasonable P/E ratio ({pe_ratio:.1f})")
                else:
                    fundamental_score -= 1  # Expensive
                    reasons.append(f"High P/E ratio ({pe_ratio:.1f})")

            # P/B Ratio
            if pb_ratio > 0:
                if pb_ratio < 1.5:
                    fundamental_score += 2  # Strong asset backing
                    reasons.append(f"Strong P/B ratio ({pb_ratio:.1f})")
                elif pb_ratio < self.pb_ratio_threshold:
                    fundamental_score += 1  # Acceptable asset backing
                    reasons.append(f"Reasonable P/B ratio ({pb_ratio:.1f})")
                else:
                    fundamental_score -= 1  # Weak asset backing
                    reasons.append(f"High P/B ratio ({pb_ratio:.1f})")

            # Debt-to-Equity
            if debt_to_equity >= 0:
                if debt_to_equity < 0.3:
                    fundamental_score += 2  # Low debt
                    reasons.append(f"Low debt-to-equity ({debt_to_equity:.2f})")
                elif debt_to_equity < self.debt_to_equity_threshold:
                    fundamental_score += 1  # Moderate debt
                    reasons.append(f"Manageable debt-to-equity ({debt_to_equity:.2f})")
                else:
                    fundamental_score -= 2  # High debt
                    reasons.append(f"High debt-to-equity ({debt_to_equity:.2f})")

            # ROE
            if roe >= 0:
                if roe > 0.25:  # 25%+ ROE
                    fundamental_score += 2  # Excellent profitability
                    reasons.append(f"Excellent ROE ({roe * 100:.1f}%)")
                elif roe > self.roe_threshold:
                    fundamental_score += 1  # Good profitability
                    reasons.append(f"Good ROE ({roe * 100:.1f}%)")
                else:
                    fundamental_score -= 1  # Poor profitability
                    reasons.append(f"Low ROE ({roe * 100:.1f}%)")

            # Current Ratio
            if current_ratio > 0:
                if current_ratio > 2:
                    fundamental_score += 1  # Strong liquidity
                    reasons.append(f"Strong current ratio ({current_ratio:.1f})")
                elif current_ratio >= self.current_ratio_threshold:
                    fundamental_score += 0  # Adequate liquidity
                    reasons.append(f"Adequate current ratio ({current_ratio:.1f})")
                else:
                    fundamental_score -= 1  # Weak liquidity
                    reasons.append(f"Low current ratio ({current_ratio:.1f})")

            # Dividend Yield
            if dividend_yield >= 0:
                if dividend_yield > 0.05:  # 5%+ dividend yield
                    fundamental_score += 2  # High dividend
                    reasons.append(f"High dividend yield ({dividend_yield * 100:.1f}%)")
                elif dividend_yield >= self.dividend_yield_threshold:
                    fundamental_score += 1  # Reasonable dividend
                    reasons.append(f"Reasonable dividend yield ({dividend_yield * 100:.1f}%)")
                # No penalty for low/no dividend - growth stocks may not pay dividends

            # Technical analysis for entry timing
            if indicators:
                rsi = indicators.get("RSI", 50)
                ma_50 = indicators.get("MA_50", live_price)
                ma_200 = indicators.get("MA_200", live_price)

                # RSI for entry timing
                if rsi < self.rsi_oversold:
                    technical_score += 1  # Good entry point
                    reasons.append(f"RSI oversold for entry ({rsi:.1f})")
                elif rsi > self.rsi_overbought:
                    technical_score -= 1  # Poor entry point
                    reasons.append(f"RSI overbought for entry ({rsi:.1f})")

                # Moving average trend
                if ma_50 > ma_200:
                    technical_score += 1  # Bullish trend
                    reasons.append("Bullish MA trend (50 > 200)")
                elif ma_50 < ma_200:
                    technical_score -= 1  # Bearish trend
                    reasons.append("Bearish MA trend (50 < 200)")

            # Calculate total score
            total_score = fundamental_score + technical_score

            # Determine investment signal
            if total_score >= 6:
                signal = "STRONG_BUY"
                confidence = min(90, 60 + total_score * 4)
            elif total_score >= 3:
                signal = "BUY"
                confidence = min(75, 50 + total_score * 4)
            elif total_score <= -3:
                signal = "STRONG_SELL"  # Only for existing positions
                confidence = min(90, 60 + abs(total_score) * 4)
            elif total_score <= 0:
                signal = "SELL"  # Only for existing positions
                confidence = min(70, 40 + abs(total_score) * 4)
            else:
                signal = "HOLD"
                confidence = 50

            # Calculate intrinsic value estimate (simplified DCF approximation)
            intrinsic_value = 0
            if book_value > 0 and roe > 0:
                # Simplified: Intrinsic Value = Book Value * (1 + ROE)^10 * 0.5 (conservative)
                growth_factor = (1 + roe) ** 10
                intrinsic_value = book_value * growth_factor * 0.5
            elif pe_ratio > 0 and (
                earnings_per_share := fundamentals.get(
                    "eps", fundamentals.get("earnings_per_share", 0)
                )
            ):
                # Using P/E approach: Intrinsic Value = EPS * Fair P/E
                fair_pe = min(18, self.pe_ratio_threshold)  # Conservative fair P/E
                intrinsic_value = earnings_per_share * fair_pe

            # Calculate margin of safety
            margin_of_safety = 0
            if intrinsic_value > 0 and live_price > 0:
                margin_of_safety = (intrinsic_value - live_price) / intrinsic_value

            return {
                "signal": signal,
                "confidence": confidence,
                "fundamental_score": fundamental_score,
                "technical_score": technical_score,
                "total_score": total_score,
                "live_price": live_price,
                "intrinsic_value_estimate": intrinsic_value,
                "margin_of_safety": margin_of_safety,
                "fundamentals": fundamentals,
                "indicators": indicators,
                "reasons": reasons,
                "timestamp": datetime.now().isoformat(),
            }

        except VendorUnavailableError as e:
            return {"signal": "HOLD", "confidence": 0, "reason": f"Vendor unavailable: {str(e)}"}
        except Exception as e:
            return {"signal": "HOLD", "confidence": 0, "reason": f"Analysis error: {str(e)}"}

    def execute_long_term_investment(
        self, ticker: str, capital_allocation: float = 0.05
    ) -> Dict[str, any]:
        """Execute a long-term investment based on strategy analysis.

        Args:
            ticker: Stock ticker symbol
            capital_allocation: Fraction of available capital to use (0.05 = 5%)

        Returns:
            Dictionary containing investment execution results
        """
        # Analyze the stock
        analysis = self.analyze_stock_for_long_term(ticker)

        # Only buy on positive signals, sell signals are for existing positions
        if analysis["signal"] not in ["BUY", "STRONG_BUY"] or analysis["confidence"] < 60:
            return {
                "success": False,
                "reason": f"No clear buy signal: {analysis.get('reason', 'Insufficient confidence')}",
                "analysis": analysis,
            }

        # Check diversification limits
        portfolio = self.wallet_manager.get_portfolio_summary()
        current_allocation = 0

        # Check current allocation to this stock
        for position in portfolio.get("positions", []):
            if position["ticker"] == ticker:
                current_value = position["market_value"]
                total_value = portfolio["total_portfolio_value"]
                current_allocation = current_value / total_value if total_value > 0 else 0
                break

        # Check if adding this position would exceed limits
        if current_allocation >= self.max_stock_allocation:
            return {
                "success": False,
                "reason": f"Already at maximum allocation for {ticker} ({current_allocation * 100:.1f}%)",
                "analysis": analysis,
            }

        # Calculate position size
        available_capital = self.wallet_manager.get_available_capital()
        investment_capital = available_capital * capital_allocation

        # Ensure we don't exceed max stock allocation
        max_investment_for_stock = portfolio["total_portfolio_value"] * self.max_stock_allocation
        current_stock_value = current_allocation * portfolio["total_portfolio_value"]
        additional_allowed = max_investment_for_stock - current_stock_value

        if additional_allowed <= 0:
            return {
                "success": False,
                "reason": f"Maximum allocation limit reached for {ticker}",
                "analysis": analysis,
            }

        investment_capital = min(investment_capital, additional_allowed)

        if investment_capital < 1000:  # Minimum investment threshold
            return {
                "success": False,
                "reason": "Insufficient capital for meaningful investment",
                "analysis": analysis,
            }

        # Calculate quantity
        live_price = analysis["live_price"]
        if live_price <= 0:
            return {"success": False, "reason": "Invalid live price", "analysis": analysis}

        quantity = int(investment_capital / live_price)

        if quantity <= 0:
            return {"success": False, "reason": "Calculated quantity is zero", "analysis": analysis}

        # Place the order (delivery trade for long-term)
        try:
            order_result = self.wallet_manager.place_order_via_broker(
                ticker=ticker,
                action="BUY",
                quantity=quantity,
                order_type="MARKET",
                price=None,
                product_type="CNC",  # Delivery order for long-term
            )

            # Record the investment
            investment_record = {
                "investment_id": f"LT_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "ticker": ticker,
                "action": "BUY",
                "quantity": quantity,
                "price": live_price,
                "order_id": order_result.get("order_id"),
                "timestamp": datetime.now().isoformat(),
                "strategy": self.name,
                "analysis": analysis,
                "investment_horizon": "long_term",  # 1+ years
            }

            self.wallet_manager.transaction_history.append(investment_record)

            return {
                "success": True,
                "investment_record": investment_record,
                "order_result": order_result,
                "analysis": analysis,
            }

        except VendorUnavailableError as e:
            return {
                "success": False,
                "reason": f"Broker unavailable: {str(e)}",
                "analysis": analysis,
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Order execution failed: {str(e)}",
                "analysis": analysis,
            }

    def evaluate_existing_positions(self) -> Dict[str, any]:
        """Evaluate existing positions for potential profit booking or stop loss."""
        try:
            portfolio = self.wallet_manager.get_portfolio_summary()
            positions = portfolio.get("positions", [])

            evaluations = []

            for position in positions:
                ticker = position["ticker"]

                # Analyze current position
                analysis = self.analyze_stock_for_long_term(ticker)

                # Determine action based on analysis
                current_price = position["current_price"]
                avg_price = position["average_price"]
                pnl_percent = position["unrealized_pnl_percent"]

                action = "HOLD"
                reason = ""

                if analysis["signal"] in ["STRONG_SELL", "SELL"] and analysis["confidence"] >= 70:
                    if pnl_percent > 0:
                        action = "SELL"
                        reason = f"Sell signal with profit ({pnl_percent:.1f}%)"
                    else:
                        action = "SELL"  # Cut losses
                        reason = f"Sell signal to limit loss ({pnl_percent:.1f}%)"
                elif analysis["signal"] in ["STRONG_BUY", "BUY"] and analysis["confidence"] >= 70:
                    action = "BUY_MORE"  # Add to position
                    reason = f"Strong buy signal for averaging up"
                elif pnl_percent > 20:  # Profit booking at 20%
                    action = "SELL_PARTIAL"
                    reason = f"Profit booking target reached ({pnl_percent:.1f}%)"
                elif pnl_percent < -10:  # Stop loss at -10%
                    action = "SELL"
                    reason = f"Stop loss triggered ({pnl_percent:.1f}%)"
                else:
                    action = "HOLD"
                    reason = "No action required"

                evaluations.append(
                    {
                        "ticker": ticker,
                        "current_price": current_price,
                        "average_price": avg_price,
                        "quantity": position["quantity"],
                        "market_value": position["market_value"],
                        "unrealized_pnl": position["unrealized_pnl"],
                        "unrealized_pnl_percent": pnl_percent,
                        "action": action,
                        "reason": reason,
                        "analysis": analysis,
                    }
                )

            return {
                "success": True,
                "evaluations": evaluations,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            return {"success": False, "reason": f"Position evaluation failed: {str(e)}"}


# Global long-term strategy instance
long_term_strategy = LongTermInvestmentStrategy()
