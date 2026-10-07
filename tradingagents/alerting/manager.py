from typing import Annotated, Dict, List, Optional, Callable
from datetime import datetime, timedelta
import time
import threading
import json

from tradingagents.wallet.manager import WalletManager
from tradingagents.dataflows.vendors.kotak_neo.trading import get_live_price as kotak_neo_get_live_price
from tradingagents.dataflows.vendors.screener_in.fundamentals import get_fundamentals as screener_get_fundamentals
from tradingagents.dataflows.vendors.moneycontrol.fundamentals import get_fundamentals as moneycontrol_get_fundamentals
from tradingagents.dataflows.vendors.tradingview.technical_indicators import get_technical_indicators
from tradingagents.dataflows.errors import VendorUnavailableError


class AlertType:
    """Types of alerts that can be triggered."""
    PRICE_TARGET = "price_target"
    SENTIMENT_CHANGE = "sentiment_change"
    VOLUME_SPIKE = "volume_spike"
    NEWS_ALERT = "news_alert"
    TECHNICAL_BREAKOUT = "technical_breakout"
    INSTITUTIONAL_FLOW = "institutional_flow"


class AlertSeverity:
    """Severity levels for alerts."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertManager:
    """Manages alerts and notifications for the trading agent."""

    def __init__(self, wallet_manager: WalletManager = None):
        self.wallet_manager = wallet_manager or WalletManager()
        self.alerts: List[Dict] = []
        self.alert_handlers: Dict[str, List[Callable]] = {
            AlertType.PRICE_TARGET: [],
            AlertType.SENTIMENT_CHANGE: [],
            AlertType.VOLUME_SPIKE: [],
            AlertType.NEWS_ALERT: [],
            AlertType.TECHNICAL_BREAKOUT: [],
            AlertType.INSTITUTIONAL_FLOW: []
        }
        self.monitoring_threads: Dict[str, threading.Thread] = {}
        self.is_monitoring = False
        self.alert_cooldowns: Dict[str, datetime] = {}  # Prevent alert spam
        self.cooldown_period = timedelta(minutes=15)  # Default cooldown period

    def register_alert_handler(self, alert_type: str, handler: Callable[[Dict], None]):
        """Register a handler function for a specific alert type.

        Args:
            alert_type: Type of alert to handle
            handler: Function to call when alert is triggered
        """
        if alert_type in self.alert_handlers:
            self.alert_handlers[alert_type].append(handler)
        else:
            raise ValueError(f"Unsupported alert type: {alert_type}")

    def set_cooldown_period(self, minutes: int):
        """Set the cooldown period to prevent alert spam.

        Args:
            minutes: Cooldown period in minutes
        """
        self.cooldown_period = timedelta(minutes=minutes)

    def _is_in_cooldown(self, alert_key: str) -> bool:
        """Check if an alert is in cooldown period.

        Args:
            alert_key: Unique identifier for the alert

        Returns:
            True if in cooldown, False otherwise
        """
        if alert_key not in self.alert_cooldowns:
            return False

        return datetime.now() < self.alert_cooldowns[alert_key]

    def _set_cooldown(self, alert_key: str):
        """Set cooldown for an alert.

        Args:
            alert_key: Unique identifier for the alert
        """
        self.alert_cooldowns[alert_key] = datetime.now() + self.cooldown_period

    def _trigger_alert(self, alert_type: str, alert_data: Dict):
        """Trigger an alert and notify all registered handlers.

        Args:
            alert_type: Type of alert to trigger
            alert_data: Data associated with the alert
        """
        # Create alert record
        alert_record = {
            "id": f"{alert_type}_{int(time.time())}",
            "type": alert_type,
            "timestamp": datetime.now().isoformat(),
            "data": alert_data
        }

        # Add to alerts list
        self.alerts.append(alert_record)

        # Keep only last 1000 alerts to prevent memory growth
        if len(self.alerts) > 1000:
            self.alerts = self.alerts[-1000:]

        # Notify handlers
        handlers = self.alert_handlers.get(alert_type, [])
        for handler in handlers:
            try:
                handler(alert_record)
            except Exception as e:
                print(f"Error in alert handler: {e}")

    def create_price_target_alert(self,
                                 ticker: str,
                                 target_price: float,
                                 condition: str = "above",  # "above" or "below"
                                 severity: str = AlertSeverity.MEDIUM) -> str:
        """Create a price target alert.

        Args:
            ticker: Stock ticker symbol
            target_price: Target price to trigger alert
            condition: "above" or "below" - trigger when price goes above/below target
            severity: Alert severity level

        Returns:
            Alert ID
        """
        alert_key = f"price_target_{ticker}_{target_price}_{condition}"

        # Check cooldown
        if self._is_in_cooldown(alert_key):
            return ""  # Return empty string if in cooldown

        def check_price_target():
            try:
                live_price = kotak_neo_get_live_price(ticker)
                if live_price <= 0:
                    return False

                if condition == "above" and live_price >= target_price:
                    return True
                elif condition == "below" and live_price <= target_price:
                    return True
                return False
            except VendorUnavailableError:
                return False
            except Exception:
                return False

        # Check if condition is met
        if check_price_target():
            alert_data = {
                "ticker": ticker,
                "target_price": target_price,
                "condition": condition,
                "current_price": kotak_neo_get_live_price(ticker),
                "severity": severity,
                "message": f"{ticker} price is {condition} {target_price}"
            }

            self._trigger_alert(AlertType.PRICE_TARGET, alert_data)
            self._set_cooldown(alert_key)

            return alert_record["id"]

        return ""

    def create_sentiment_change_alert(self,
                                    ticker: str,
                                    sentiment_threshold: float = 0.3,  # -1 to 1 scale
                                    severity: str = AlertSeverity.MEDIUM) -> str:
        """Create a sentiment change alert.

        Args:
            ticker: Stock ticker symbol
            sentiment_threshold: Threshold for sentiment change to trigger alert
            severity: Alert severity level

        Returns:
            Alert ID
        """
        alert_key = f"sentiment_change_{ticker}_{sentiment_threshold}"

        # Check cooldown
        if self._is_in_cooldown(alert_key):
            return ""

        def check_sentiment_change():
            try:
                # This would typically compare current sentiment to previous value
                # For simplicity, we'll check if sentiment exceeds threshold
                # In a real implementation, you'd store previous sentiment values
                fundamentals_screener = screener_get_fundamentals(ticker)
                # Assuming sentiment is included in fundamentals or we'd use a sentiment analyst
                sentiment_score = fundamentals_screener.get("sentiment_score", 0)
                return abs(sentiment_score) >= sentiment_threshold
            except VendorUnavailableError:
                try:
                    fundamentals_moneycontrol = moneycontrol_get_fundamentals(ticker)
                    sentiment_score = fundamentals_moneycontrol.get("sentiment_score", 0)
                    return abs(sentiment_score) >= sentiment_threshold
                except:
                    return False
            except Exception:
                return False

        # Check if condition is met
        if check_sentiment_change():
            alert_data = {
                "ticker": ticker,
                "sentiment_threshold": sentiment_threshold,
                "current_sentiment": 0.5,  # Placeholder - would be actual value
                "severity": severity,
                "message": f"{ticker} sentiment changed significantly"
            }

            self._trigger_alert(AlertType.SENTIMENT_CHANGE, alert_data)
            self._set_cooldown(alert_key)

            return alert_record["id"]

        return ""

    def create_volume_spike_alert(self,
                                ticker: str,
                                volume_multiplier: float = 2.0,  # 2x average volume
                                severity: str = AlertSeverity.MEDIUM) -> str:
        """Create a volume spike alert.

        Args:
            ticker: Stock ticker symbol
            volume_multiplier: Multiple of average volume to trigger alert
            severity: Alert severity level

        Returns:
            Alert ID
        """
        alert_key = f"volume_spike_{ticker}_{volume_multiplier}"

        # Check cooldown
        if self._is_in_cooldown(alert_key):
            return ""

        def check_volume_spike():
            try:
                # This would require fetching volume data and comparing to average
                # For simulation, we'll return True randomly based on ticker hash
                # In real implementation, you'd fetch actual volume data
                import hashlib
                volume_ratio = (hashlib.md5(ticker.encode()).hexdigest()[:8], 16) / (16**8) * 5  # 0-5x
                return volume_ratio >= volume_multiplier
            except Exception:
                return False

        # Check if condition is met
        if check_volume_spike():
            alert_data = {
                "ticker": ticker,
                "volume_multiplier": volume_multiplier,
                "current_volume_ratio": 2.5,  # Placeholder
                "severity": severity,
                "message": f"{ticker} experiencing volume spike ({volume_multiplier}x average)"
            }

            self._trigger_alert(AlertType.VOLUME_SPIKE, alert_data)
            self._set_cooldown(alert_key)

            return alert_record["id"]

        return ""

    def create_technical_breakout_alert(self,
                                      ticker: str,
                                      breakout_type: str = "resistance",  # "resistance" or "support"
                                      severity: str = AlertSeverity.HIGH) -> str:
        """Create a technical breakout alert.

        Args:
            ticker: Stock ticker symbol
            breakout_type: Type of breakout - "resistance" or "support"
            severity: Alert severity level

        Returns:
            Alert ID
        """
        alert_key = f"technical_breakout_{ticker}_{breakout_type}"

        # Check cooldown
        if self._is_in_cooldown(alert_key):
            return ""

        def check_technical_breakout():
            try:
                # Get technical indicators
                indicators = get_technical_indicators(
                    ticker=ticker,
                    indicators=["RSI", "MOVING_AVERAGES", "BBANDS"]
                )

                if not indicators:
                    return False

                live_price = kotak_neo_get_live_price(ticker)
                if live_price <= 0:
                    return False

                # Check for resistance breakout (price above upper Bollinger Band with volume)
                if breakout_type == "resistance":
                    bb_upper = indicators.get("BBAND_upper", 0)
                    rsi = indicators.get("RSI", 50)
                    return live_price > bb_upper and rsi > 60
                # Check for support breakout (price below lower Bollinger Band)
                elif breakout_type == "support":
                    bb_lower = indicators.get("BBAND_lower", 0)
                    rsi = indicators.get("RSI", 50)
                    return live_price < bb_lower and rsi < 40

                return False
            except VendorUnavailableError:
                return False
            except Exception:
                return False

        # Check if condition is met
        if check_technical_breakout():
            alert_data = {
                "ticker": ticker,
                "breakout_type": breakout_type,
                "current_price": kotak_neo_get_live_price(ticker),
                "severity": severity,
                "message": f"{ticker} breaking {breakout_type} level"
            }

            self._trigger_alert(AlertType.TECHNICAL_BREAKOUT, alert_data)
            self._set_cooldown(alert_key)

            return alert_record["id"]

        return ""

    def create_institutional_flow_alert(self,
                                      severity: str = AlertSeverity.HIGH) -> str:
        """Create an institutional flow alert.

        Args:
            severity: Alert severity level

        Returns:
            Alert ID
        """
        alert_key = f"institutional_flow_{datetime.now().strftime('%Y%m%d')}"

        # Check cooldown (daily cooldown for institutional alerts)
        if self._is_in_cooldown(alert_key):
            return ""

        def check_institutional_flow():
            try:
                # Get institutional sentiment
                from tradingagents.analysis.institutional.flow_analyzer import institutional_flow_analyzer
                sentiment_data = institutional_flow_analyzer.get_institutional_sentiment()

                # Trigger alert on strong institutional sentiment
                sentiment = sentiment_data.get("sentiment", "Neutral")
                confidence = sentiment_data.get("confidence", 0)

                return sentiment in ["Very Bullish", "Very Bearish"] and confidence >= 80
            except Exception:
                return False

        # Check if condition is met
        if check_institutional_flow():
            alert_data = {
                "sentiment": "Very Bullish",  # Placeholder
                "confidence": 85,  # Placeholder
                "severity": severity,
                "message": "Strong institutional flow detected"
            }

            self._trigger_alert(AlertType.INSTITUTIONAL_FLOW, alert_data)
            self._set_cooldown(alert_key)

            return alert_record["id"]

        return ""

    def start_monitoring(self,
                        tickers: List[str] = None,
                        check_interval: int = 30):  # seconds
        """Start monitoring for alerts.

        Args:
            tickers: List of tickers to monitor (None for wallet positions)
            check_interval: Interval between checks in seconds
        """
        if self.is_monitoring:
            return

        self.is_monitoring = True

        def monitor_loop():
            while self.is_monitoring:
                try:
                    # Get tickers to monitor
                    if tickers is None:
                        # Monitor positions in wallet
                        portfolio = self.wallet_manager.get_portfolio_summary()
                        tickers_to_monitor = [pos["ticker"] for pos in portfolio.get("positions", [])]
                    else:
                        tickers_to_monitor = tickers

                    # Check each ticker for alerts
                    for ticker in tickers_to_monitor:
                        # Price target alerts (would need to be configured separately)
                        # Sentiment change alerts
                        self.create_sentiment_change_alert(ticker, severity=AlertSeverity.MEDIUM)

                        # Volume spike alerts
                        self.create_volume_spike_alert(ticker, severity=AlertSeverity.MEDIUM)

                        # Technical breakout alerts
                        self.create_technical_breakout_alert(ticker, breakout_type="resistance", severity=AlertSeverity.HIGH)
                        self.create_technical_breakout_alert(ticker, breakout_type="support", severity=AlertSeverity.HIGH)

                    # Check institutional flow (once per cycle)
                    self.create_institutional_flow_alert(severity=AlertSeverity.HIGH)

                    # Sleep until next check
                    time.sleep(check_interval)

                except Exception as e:
                    print(f"Error in monitoring loop: {e}")
                    time.sleep(check_interval)

        # Start monitoring thread
        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()
        self.monitoring_threads["main"] = monitor_thread

    def stop_monitoring(self):
        """Stop monitoring for alerts."""
        self.is_monitoring = False
        # Wait for threads to finish (in practice, you'd use proper thread synchronization)
        time.sleep(2)

    def get_recent_alerts(self, limit: int = 50) -> List[Dict]:
        """Get recent alerts.

        Args:
            limit: Maximum number of alerts to return

        Returns:
            List of recent alerts
        """
        return self.alerts[-limit:] if self.alerts else []

    def get_alerts_by_type(self, alert_type: str, limit: int = 50) -> List[Dict]:
        """Get alerts by type.

        Args:
            alert_type: Type of alerts to retrieve
            limit: Maximum number of alerts to return

        Returns:
            List of alerts of specified type
        """
        filtered_alerts = [alert for alert in self.alerts if alert["type"] == alert_type]
        return filtered_alerts[-limit:] if filtered_alerts else []

    def clear_alerts(self, older_than: Optional[datetime] = None):
        """Clear alerts.

        Args:
            older_than: Clear alerts older than this datetime (None for all)
        """
        if older_than is None:
            self.alerts.clear()
            self.alert_cooldowns.clear()
        else:
            self.alerts = [
                alert for alert in self.alerts
                if datetime.fromisoformat(alert["timestamp"]) >= older_than
            ]
            # Also clean up cooldowns for removed alerts
            # In practice, you'd want to be more careful about this
            self.alert_cooldowns.clear()


# Global alert manager instance
alert_manager = AlertManager()