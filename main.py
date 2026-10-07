"""
Main entry point for the Indian Market Stock Analysis Agent.
Demonstrates the capabilities of the extended TradingAgents framework
with Indian market data vendors, trading strategies, and alerting system.
"""

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

# Import our new components
from tradingagents.wallet.manager import WalletManager
from tradingagents.strategies.intraday import IntradayTradingStrategy
from tradingagents.strategies.long_term import LongTermInvestmentStrategy
from tradingagents.analysis.institutional.flow_analyzer import InstitutionalFlowAnalyzer
from tradingagents.analysis.mutual_funds.analyzer import MutualFundAnalyzer
from tradingagents.alerting.manager import AlertManager, AlertType, AlertSeverity

# Initialize wallet manager for paper trading (set paper_trading=False for live trading)
wallet_config = WalletManager.WalletConfig(
    initial_capital=500000.0,  # ₹5 lakhs initial capital
    risk_per_trade=0.02,       # 2% risk per trade
    broker="kotak_neo",        # Using Kotak Neo for algo trading
    paper_trading=True         # Set to False for live trading
)
wallet_manager = WalletManager(wallet_config)

# Initialize strategies
intraday_strategy = IntradayTradingStrategy(wallet_manager)
long_term_strategy = LongTermInvestmentStrategy(wallet_manager)

# Initialize analyzers
institutional_analyzer = InstitutionalFlowAnalyzer()
mutual_fund_analyzer = MutualFundAnalyzer()
alert_manager = AlertManager(wallet_manager)

# Example alert handler functions
def price_alert_handler(alert):
    print(f"🚨 PRICE ALERT: {alert['data']['message']}")

def sentiment_alert_handler(alert):
    print(f"📊 SENTIMENT ALERT: {alert['data']['message']}")

def volume_alert_handler(alert):
    print(f"📈 VOLUME ALERT: {alert['data']['message']}")

# Register alert handlers
alert_manager.register_alert_handler(AlertType.PRICE_TARGET, price_alert_handler)
alert_manager.register_alert_handler(AlertType.SENTIMENT_CHANGE, sentiment_alert_handler)
alert_manager.register_alert_handler(AlertType.VOLUME_SPIKE, volume_alert_handler)

# Set up alert cooldowns
alert_manager.set_cooldown_period(15)  # 15 minutes cooldown

# DEFAULT_CONFIG already applies TRADINGAGENTS_* env-var overrides
# (llm_provider, deep_think_llm, quick_think_llm, backend_url, etc.),
# so users can switch models or endpoints purely via .env without
# editing this script. Override individual keys here only when you
# want a hard-coded value that should ignore the environment.
config = DEFAULT_CONFIG.copy()

# Configure for Indian market (NSE/BSE)
config.update({
    "llm_provider": "openai",
    "deep_think_llm": "gpt-6-sol",
    "quick_think_llm": "gpt-6-luna",
})

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

def demonstrate_wallet_management():
    """Demonstrate wallet and portfolio management capabilities."""
    print("=== WALLET MANAGEMENT DEMO ===")
    wallet_info = wallet_manager.initialize_wallet()
    print(f"Wallet ID: {wallet_info['wallet_id']}")
    print(f"Initial Capital: ₹{wallet_info['initial_capital']:,.2f}")
    print(f"Current Cash: ₹{wallet_info['current_cash']:,.2f}")
    print(f"Broker: {wallet_info['broker']}")
    print(f"Paper Trading: {wallet_info['paper_trading']}")
    print()

def demonstrate_data_vendors():
    """Demonstrate Indian market data vendors."""
    print("=== INDIAN MARKET DATA VENDORS DEMO ===")

    # Test screener.in
    try:
        from tradingagents.dataflows.vendors.screener_in.fundamentals import get_fundamentals as screener_fundamentals
        fundamentals = screener_fundamentals("RELIANCE")
        print(f"Screener.in - RELIANCE: {fundamentals.get('company_name', 'N/A')}")
        print(f"  Current Price: ₹{fundamentals.get('current_price', 0):,.2f}")
        print(f"  P/E Ratio: {fundamentals.get('pe_ratio', 'N/A')}")
    except Exception as e:
        print(f"Screener.in demo error: {e}")

    # Test moneycontrol
    try:
        from tradingagents.dataflows.vendors.moneycontrol.fundamentals import get_fundamentals as moneycontrol_fundamentals
        fundamentals = moneycontrol_fundamentals("TCS")
        print(f"Moneycontrol - TCS: {fundamentals.get('company_name', 'N/A')}")
        print(f"  Current Price: ₹{fundamentals.get('current_price', 0):,.2f}")
        print(f"  P/E Ratio: {fundamentals.get('pe_ratio', 'N/A')}")
    except Exception as e:
        print(f"Moneycontrol demo error: {e}")

    # Test tradingview technical indicators
    try:
        from tradingagents.dataflows.vendors.tradingview.technical_indicators import get_technical_indicators
        indicators = get_technical_indicators("RELIANCE.NS", ["RSI", "MACD"])
        print(f"TradingView - RELIANCE.NS:")
        print(f"  RSI: {indicators.get('RSI', 'N/A')}")
        print(f"  MACD: {indicators.get('MACD', 'N/A')}")
    except Exception as e:
        print(f"TradingView demo error: {e}")

    print()

def demonstrate_trading_strategies():
    """Demonstrate trading strategies."""
    print("=== TRADING STRATEGIES DEMO ===")

    # Demonstrate long-term investment analysis
    print("Long-Term Investment Analysis (HDFC Bank):")
    lt_analysis = long_term_strategy.analyze_stock_for_long_term("HDFCBANK.NS")
    print(f"  Signal: {lt_analysis.get('signal', 'N/A')}")
    print(f"  Confidence: {lt_analysis.get('confidence', 0)}%")
    print(f"  Live Price: ₹{lt_analysis.get('live_price', 0):,.2f}")
    if 'intrinsic_value_estimate' in lt_analysis:
        print(f"  Intrinsic Value Estimate: ₹{lt_analysis['intrinsic_value_estimate']:,.2f}")
        print(f"  Margin of Safety: {lt_analysis.get('margin_of_safety', 0):.1%}")
    print(f"  Reasons: {', '.join(lt_analysis.get('reasons', []))}")
    print()

    # Demonstrate intraday analysis
    print("Intraday Analysis (Infosys):")
    intra_analysis = intraday_strategy.analyze_stock_for_intraday("INFY.NS")
    print(f"  Signal: {intra_analysis.get('signal', 'N/A')}")
    print(f"  Confidence: {intra_analysis.get('confidence', 0)}%")
    print(f"  Entry Price: ₹{intra_analysis.get('entry_price', 0):,.2f}")
    print(f"  Stop Loss: ₹{intra_analysis.get('stop_loss', 0):,.2f}")
    print(f"  Target: ₹{intra_analysis.get('target', 0):,.2f}")
    print(f"  Reasons: {', '.join(intra_analysis.get('reasons', []))}")
    print()

def demonstrate_institutional_analysis():
    """Demonstrate institutional flow analysis."""
    print("=== INSTITUTIONAL FLOW ANALYSIS DEMO ===")

    # FII/DII data
    try:
        fii_dii = institutional_analyzer.get_fii_dii_data()
        print(f"FII/DII Flows:")
        print(f"  FII Net Buy: ₹{fii_dii.get('fii_net_buy', 0):,.2f} Crores")
        print(f"  DII Net Buy: ₹{fii_dii.get('dii_net_buy', 0):,.2f} Crores")
        print(f"  Combined Net: ₹{fii_dii.get('net_fii_dii', 0):,.2f} Crores")
        print(f"  Trend: {fii_dii.get('trend', 'N/A')}")
    except Exception as e:
        print(f"FII/DII data error: {e}")

    # Bulk deals
    try:
        bulk_deals = institutional_analyzer.get_bulk_deals_data(days=2)
        print(f"\nRecent Bulk Deals ({len(bulk_deals)} found):")
        for deal in bulk_deals[:2]:  # Show first 2
            print(f"  {deal['ticker']}: {deal['buyer_seller']} {deal['quantity']:,} shares @ ₹{deal['price']:,.2f} ({deal['institution']})")
    except Exception as e:
        print(f"Bulk deals error: {e}")

    # Mutual fund flows
    try:
        mf_flows = institutional_analyzer.get_mutual_fund_flows(days=15)
        print(f"\nMutual Fund Flows:")
        print(f"  Net Inflow: ₹{mf_flows.get('net_inflow', 0):,.2f} Crores")
        print(f"  Total AUM: ₹{mf_flows.get('total_aum', 0):,.2f} Crores")
        print(f"  Trend: {mf_flows.get('trend', 'N/A')}")
    except Exception as e:
        print(f"Mutual fund flows error: {e}")

    print()

def demonstrate_mutual_fund_analysis():
    """Demonstrate mutual fund analysis capabilities."""
    print("=== MUTUAL FUND ANALYSIS DEMO ===")

    # NAV data
    try:
        nav_data = mutual_fund_analyzer.get_mutual_fund_nav("120503")  # Example scheme code
        print(f"Mutual Fund NAV (HDFC Top 100 Fund):")
        print(f"  Scheme: {nav_data.get('scheme_name', 'N/A')}")
        print(f"  NAV: ₹{nav_data.get('nav', 0):,.2f} ({nav_data.get('nav_date', 'N/A')})")
        print(f"  AUM: ₹{nav_data.get('aum', 0):,.2f} Crores")
        print(f"  Expense Ratio: {nav_data.get('expense_ratio', 0):.2f}%")
        print(f"  Fund Manager: {nav_data.get('fund_manager', 'N/A')}")
    except Exception as e:
        print(f"Mutual fund NAV error: {e}")

    # Returns analysis
    try:
        returns_data = mutual_fund_analyzer.get_mutual_fund_returns("120503")
        print(f"\nReturns Analysis:")
        returns = returns_data.get('returns', {})
        for period, value in returns.items():
            print(f"  {period}: {value:.2f}%")
    except Exception as e:
        print(f"Mutual fund returns error: {e}")

    # Expense ratio analysis
    try:
        expense_analysis = mutual_fund_analyzer.get_expense_ratio_analysis("120503")
        print(f"\nExpense Ratio Analysis:")
        print(f"  Expense Ratio: {expense_analysis.get('expense_ratio', 0):.2f}% ({expense_analysis.get('expense_category', 'N/A')})")
        print(f"  Estimated Net Return: {expense_analysis.get('estimated_net_return', 0):.2f}%")
    except Exception as e:
        print(f"Expense ratio analysis error: {e}")

    print()

def demonstrate_alerting_system():
    """Demonstrate alerting and notification system."""
    print("=== ALERTING SYSTEM DEMO ===")

    # Create some sample alerts
    print("Setting up sample alerts...")

    # Price target alert for Reliance
    alert_id = alert_manager.create_price_target_alert(
        ticker="RELIANCE.NS",
        target_price=2500.0,
        condition="above",
        severity=AlertSeverity.MEDIUM
    )
    if alert_id:
        print(f"✅ Price target alert set for RELIANCE.NS above ₹2500")
    else:
        print(f"⚠️  Price target alert not set (in cooldown or error)")

    # Volume spike alert for TCS
    alert_id = alert_manager.create_volume_spike_alert(
        ticker="TCS.NS",
        volume_multiplier=2.5,
        severity=AlertSeverity.HIGH
    )
    if alert_id:
        print(f"✅ Volume spike alert set for TCS.NS (2.5x average volume)")
    else:
        print(f"⚠️  Volume spike alert not set (in cooldown or error)")

    # Show recent alerts
    print(f"\nRecent Alerts ({len(alert_manager.get_recent_alerts())} total):")
    recent_alerts = alert_manager.get_recent_alerts(5)
    for alert in recent_alerts:
        print(f"  [{alert['type']}] {alert['data']['message']}")

    print()

def demonstrate_trading_execution():
    """Demonstrate trade execution capabilities."""
    print("=== TRADING EXECUTION DEMO ===")

    # Show current portfolio
    portfolio = wallet_manager.get_portfolio_summary()
    print(f"Current Portfolio Value: ₹{portfolio['total_portfolio_value']:,.2f}")
    print(f"Cash Available: ₹{portfolio['cash']:,.2f}")
    print(f"Positions: {portfolio['positions_count']}")

    if portfolio['positions_count'] > 0:
        print("Current Holdings:")
        for position in portfolio['positions'][:3]:  # Show first 3 positions
            print(f"  {position['ticker']}: {position['quantity']} shares @ ₹{position['average_price']:,.2f}")
            print(f"    Current: ₹{position['current_price']:,.2f} | P&L: ₹{position['unrealized_pnl']:,.2f} ({position['unrealized_pnl_percent']:+.2f}%)")
    else:
        print("No current positions")

    print("\nNote: Actual trade execution would require:")
    print("- Live market connection")
    print("- Valid API credentials for Kotak Neo")
    print("- Sufficient funds in account")
    print("- Market hours (9:15 AM - 3:30 PM IST)")
    print()

def main():
    """Main demonstration function."""
    print("🇮🇳 INDIAN MARKET STOCK ANALYSIS AGENT 🇮🇳")
    print("=" * 50)
    print("Extended TradingAgents Framework with:")
    print("• Indian Market Data Vendors (Screener.in, Moneycontrol, TradingView)")
    print("• Brokerage Integration (Kotak Neo API for algo trading)")
    print("• Wallet & Portfolio Management")
    print("• Intraday & Long-Term Trading Strategies")
    print("• Institutional Flow Analysis (FII/DII, Bulk/Block Deals, MF Flows)")
    print("• Mutual Fund Analysis (NAV, Returns, Expense Ratios, Fund Managers)")
    print("• Alerting System (Price, Sentiment, Volume, Technical Breakouts)")
    print("=" * 50)
    print()

    # Run all demonstrations
    demonstrate_wallet_management()
    demonstrate_data_vendors()
    demonstrate_trading_strategies()
    demonstrate_institutional_analysis()
    demonstrate_mutual_fund_analysis()
    demonstrate_alerting_system()
    demonstrate_trading_execution()

    print("🎯 DEMONSTRATION COMPLETE")
    print("To use this agent for live trading:")
    print("1. Set paper_trading=False in WalletManager config")
    print("2. Configure valid Kotak Neo API credentials")
    print("3. Run during market hours (9:15 AM - 3:30 PM IST)")
    print("4. Monitor alerts and adjust strategies as needed")

if __name__ == "__main__":
    main()