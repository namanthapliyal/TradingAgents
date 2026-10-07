from typing import Annotated, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import uuid

from tradingagents.dataflows.vendors.kotak_neo.trading import place_order as kotak_neo_place_order, get_holdings as kotak_neo_get_holdings, get_funds as kotak_neo_get_funds
from tradingagents.dataflows.vendors.interactive_brokers.trading import place_order as ib_place_order, get_portfolio as ib_get_portfolio, get_account_summary as ib_get_account_summary
from tradingagents.dataflows.errors import VendorUnavailableError


@dataclass
class Position:
    """Represents a single position in the portfolio."""
    ticker: str
    company_name: str
    quantity: int
    average_price: float
    current_price: float = 0.0
    market_value: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_percent: float = 0.0
    product_type: str = "CNC"  # MIS for intraday, CNC for delivery
    exchange: str = "NSE"
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Order:
    """Represents a trading order."""
    order_id: str
    ticker: str
    action: str  # BUY or SELL
    quantity: int
    order_type: str  # MARKET, LIMIT, etc.
    price: Optional[float]
    product_type: str
    status: str
    timestamp: datetime
    filled_quantity: int = 0
    average_price: float = 0.0


@dataclass
class WalletConfig:
    """Configuration for the wallet."""
    initial_capital: float = 100000.0
    risk_per_trade: float = 0.02  # 2% risk per trade
    max_positions: int = 10
    stop_loss_percent: float = 0.05  # 5% stop loss
    target_profit_percent: float = 0.10  # 10% target profit
    broker: str = "kotak_neo"  # kotak_neo or interactive_brokers
    paper_trading: bool = True  # Set to False for live trading


class WalletManager:
    """Manages the agent's wallet, portfolio, and trading operations."""

    def __init__(self, config: WalletConfig = None):
        self.config = config or WalletConfig()
        self.cash = self.config.initial_capital
        self.positions: Dict[str, Position] = {}
        self.orders: List[Order] = []
        self.transaction_history: List[Dict] = []
        self.wallet_id = str(uuid.uuid4())

    def initialize_wallet(self) -> Dict[str, any]:
        """Initialize the wallet and return initial state."""
        return {
            "wallet_id": self.wallet_id,
            "initial_capital": self.config.initial_capital,
            "current_cash": self.cash,
            "broker": self.config.broker,
            "paper_trading": self.config.paper_trading,
            "timestamp": datetime.now().isoformat()
        }

    def get_total_portfolio_value(self) -> float:
        """Calculate total portfolio value (cash + positions)."""
        positions_value = sum(
            position.market_value for position in self.positions.values()
        )
        return self.cash + positions_value

    def get_available_capital(self) -> float:
        """Get available capital for new trades."""
        # Calculate margin used by current positions
        margin_used = sum(
            position.quantity * position.average_price * 0.2  # Assuming 20% margin requirement
            for position in self.positions.values()
        )
        return max(0, self.cash - margin_used)

    def calculate_position_size(self, ticker: str, entry_price: float, stop_loss_price: float) -> int:
        """Calculate position size based on risk management."""
        if self.config.risk_per_trade <= 0 or entry_price <= 0:
            return 0

        risk_per_share = abs(entry_price - stop_loss_price)
        if risk_per_share <= 0:
            return 0

        risk_amount = self.get_total_portfolio_value() * self.config.risk_per_trade
        position_size = int(risk_amount / risk_per_share)

        # Limit by available capital
        max_affordable_shares = int(self.get_available_capital() / entry_price)
        return min(position_size, max_affordable_shares)

    def add_position(self, ticker: str, company_name: str, quantity: int,
                    price: float, product_type: str = "CNC", exchange: str = "NSE") -> bool:
        """Add a new position to the portfolio."""
        try:
            if ticker in self.positions:
                # Average up/down existing position
                existing = self.positions[ticker]
                total_quantity = existing.quantity + quantity
                total_cost = (existing.quantity * existing.average_price) + (quantity * price)
                new_avg_price = total_cost / total_quantity if total_quantity > 0 else 0

                existing.quantity = total_quantity
                existing.average_price = new_avg_price
            else:
                # Create new position
                self.positions[ticker] = Position(
                    ticker=ticker,
                    company_name=company_name,
                    quantity=quantity,
                    average_price=price,
                    product_type=product_type,
                    exchange=exchange
                )

            # Update cash (for BUY operations)
            self.cash -= quantity * price

            return True
        except Exception as e:
            print(f"Error adding position: {e}")
            return False

    def remove_position(self, ticker: str, quantity: int, price: float) -> bool:
        """Remove or reduce a position from the portfolio."""
        try:
            if ticker not in self.positions:
                return False

            position = self.positions[ticker]

            if quantity >= position.quantity:
                # Close entire position
                pnl = (price - position.average_price) * position.quantity
                self.cash += position.quantity * price
                del self.positions[ticker]
            else:
                # Reduce position
                position.quantity -= quantity
                self.cash += quantity * price

                # If quantity becomes zero, remove position
                if position.quantity <= 0:
                    del self.positions[ticker]

            return True
        except Exception as e:
            print(f"Error removing position: {e}")
            return False

    def update_position_prices(self, price_data: Dict[str, float]):
        """Update current prices for all positions."""
        for ticker, position in self.positions.items():
            if ticker in price_data:
                position.current_price = price_data[ticker]
                position.market_value = position.quantity * position.current_price
                position.unrealized_pnl = (position.current_price - position.average_price) * position.quantity
                if position.average_price > 0:
                    position.unrealized_pnl_percent = (
                        (position.current_price - position.average_price) / position.average_price
                    ) * 100

    def place_order_via_broker(self, ticker: str, action: str, quantity: int,
                              order_type: str = "MARKET", price: Optional[float] = None,
                              product_type: str = "CNC") -> Dict[str, any]:
        """Place an order via the configured broker."""
        try:
            if self.config.broker == "kotak_neo":
                if self.config.paper_trading:
                    # Simulate order for paper trading
                    order_result = {
                        "order_id": f"PAPER_{uuid.uuid4().hex[:8]}",
                        "status": "COMPLETE" if order_type == "MARKET" else "OPEN",
                        "ticker": ticker,
                        "action": action,
                        "quantity": quantity,
                        "order_type": order_type,
                        "price": price,
                        "product_type": product_type,
                        "timestamp": datetime.now().isoformat()
                    }

                    # Update portfolio immediately for paper trading
                    if action.upper() == "BUY":
                        self.add_position(ticker, ticker, quantity, price or 0, product_type)
                    elif action.upper() == "SELL":
                        self.remove_position(ticker, quantity, price or 0)

                    return order_result
                else:
                    # Live trading with Kotak Neo
                    return kotak_neo_place_order(ticker, action, quantity, order_type, price, product_type)

            elif self.config.broker == "interactive_brokers":
                if self.config.paper_trading:
                    # Simulate order for paper trading
                    order_result = {
                        "order_id": f"IB_PAPER_{uuid.uuid4().hex[:8]}",
                        "status": "COMPLETE" if order_type == "MKT" else "SUBMITTED",
                        "ticker": ticker,
                        "action": action,
                        "quantity": quantity,
                        "order_type": order_type,
                        "price": price,
                        "product_type": product_type,
                        "timestamp": datetime.now().isoformat()
                    }

                    # Update portfolio immediately for paper trading
                    if action.upper() == "BUY":
                        self.add_position(ticker, ticker, quantity, price or 0, product_type)
                    elif action.upper() == "SELL":
                        self.remove_position(ticker, quantity, price or 0)

                    return order_result
                else:
                    # Live trading with Interactive Brokers
                    # Note: Interactive Brokers uses different order type conventions
                    ib_order_type = {
                        "MARKET": "MKT",
                        "LIMIT": "LMT",
                        "STOP_LOSS": "STP"
                    }.get(order_type, "MKT")

                    return ib_place_order(ticker, action, quantity, ib_order_type, price)

            else:
                raise ValueError(f"Unsupported broker: {self.config.broker}")

        except VendorUnavailableError as e:
            # Fall back to paper trading if broker is unavailable
            if not self.config.paper_trading:
                print(f"Broker unavailable ({e}), falling back to paper trading")
                # Temporarily switch to paper trading
                original_broker = self.config.broker
                self.config.broker = "kotak_neo"  # Default to Kotak Neo for paper trading
                result = self.place_order_via_broker(ticker, action, quantity, order_type, price, product_type)
                self.config.broker = original_broker
                return result
            else:
                raise e
        except Exception as e:
            raise VendorUnavailableError(f"Failed to place order: {str(e)}")

    def get_portfolio_summary(self) -> Dict[str, any]:
        """Get a summary of the current portfolio."""
        total_value = self.get_total_portfolio_value()
        total_cost = sum(
            position.quantity * position.average_price
            for position in self.positions.values()
        )
        total_pnl = total_value - total_cost
        total_pnl_percent = (total_pnl / total_cost * 100) if total_cost > 0 else 0

        return {
            "wallet_id": self.wallet_id,
            "cash": self.cash,
            "positions_count": len(self.positions),
            "total_portfolio_value": total_value,
            "total_cost": total_cost,
            "total_unrealized_pnl": total_pnl,
            "total_unrealized_pnl_percent": total_pnl_percent,
            "positions": [
                {
                    "ticker": pos.ticker,
                    "company_name": pos.company_name,
                    "quantity": pos.quantity,
                    "average_price": pos.average_price,
                    "current_price": pos.current_price,
                    "market_value": pos.market_value,
                    "unrealized_pnl": pos.unrealized_pnl,
                    "unrealized_pnl_percent": pos.unrealized_pnl_percent,
                    "product_type": pos.product_type,
                    "exchange": pos.exchange
                }
                for pos in self.positions.values()
            ],
            "timestamp": datetime.now().isoformat()
        }

    def reset_wallet(self, new_capital: Optional[float] = None):
        """Reset the wallet to initial state."""
        if new_capital is not None:
            self.config.initial_capital = new_capital
        self.cash = self.config.initial_capital
        self.positions.clear()
        self.orders.clear()
        self.transaction_history.clear()
        self.wallet_id = str(uuid.uuid4())


# Global wallet instance (in practice, this would be managed more carefully)
wallet_manager = WalletManager()