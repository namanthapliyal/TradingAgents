from typing import Annotated, Dict, List, Optional
from datetime import datetime, timedelta
import requests
import pandas as pd

from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.net import vendor_reachable


class InstitutionalFlowAnalyzer:
    """Analyzes institutional flows including FII/DII, bulk/block deals, and mutual fund activities."""

    def __init__(self):
        self.name = "Institutional Flow Analyzer"

    def get_fii_dii_data(self) -> Dict[str, any]:
        """Get FII/DII (Foreign/Domestic Institutional Investor) flow data.

        Returns:
            Dictionary containing FII/DII buying/selling activity
        """
        try:
            # In a real implementation, this would fetch from sources like:
            # - NSE/BSE websites
            # - Financial data APIs (Moneycontrol, Screener.in, etc.)
            # - RBI or SEBI reports

            # For now, return simulated data based on typical patterns
            # In production, this would be replaced with actual API calls

            # Simulate fetching FII/DII data
            fii_dii_data = {
                "fii_net_buy": 1250.50,  # In Crores INR
                "dii_net_buy": 890.25,   # In Crores INR
                "fii_buy": 2100.75,
                "fii_sell": 850.25,
                "dii_buy": 1500.50,
                "dii_sell": 610.25,
                "net_fii_dii": 2140.75,  # Combined net buying
                "trend": "bullish" if (1250.50 + 890.25) > 0 else "bearish",
                "consecutive_days_buying": 3,
                "latest_update": datetime.now().strftime("%Y-%m-%d"),
                "data_source": "simulated"  # Would be "nse", "bse", "moneycontrol", etc. in real implementation
            }

            return fii_dii_data

        except Exception as e:
            raise VendorUnavailableError(f"Failed to fetch FII/DII data: {str(e)}")

    def get_bulk_deals_data(self, days: int = 7) -> List[Dict[str, any]]:
        """Get bulk deal data from exchanges.

        Args:
            days: Number of days to look back for bulk deals

        Returns:
            List of dictionaries containing bulk deal information
        """
        try:
            # In a real implementation, this would fetch from:
            # - NSE/BSE bulk deal windows
            # - Financial data APIs
            # - Exchange filings

            # Simulate bulk deals data
            bulk_deals = [
                {
                    "date": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
                    "ticker": "RELIANCE.NS",
                    "company_name": "Reliance Industries Limited",
                    "buyer_seller": "Buyer",
                    "quantity": 2500000,
                    "price": 2475.50,
                    "value": 618875000,  # Quantity * Price
                    "institution": "LIC of India",
                    "type": "Bulk Deal"
                },
                {
                    "date": (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d"),
                    "ticker": "TCS.NS",
                    "company_name": "Tata Consultancy Services Limited",
                    "buyer_seller": "Seller",
                    "quantity": 1800000,
                    "price": 3240.25,
                    "value": 583245000,
                    "institution": "Government of Singapore",
                    "type": "Bulk Deal"
                },
                {
                    "date": (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d"),
                    "ticker": "INFY.NS",
                    "company_name": "Infosys Limited",
                    "buyer_seller": "Buyer",
                    "quantity": 3200000,
                    "price": 1645.75,
                    "value": 526640000,
                    "institution": "HDFC Mutual Fund",
                    "type": "Bulk Deal"
                }
            ]

            # Filter by date range
            cutoff_date = datetime.now() - timedelta(days=days)
            filtered_deals = [
                deal for deal in bulk_deals
                if datetime.strptime(deal["date"], "%Y-%m-%d") >= cutoff_date
            ]

            return filtered_deals

        except Exception as e:
            raise VendorUnavailableError(f"Failed to fetch bulk deals data: {str(e)}")

    def get_block_deals_data(self, days: int = 7) -> List[Dict[str, any]]:
        """Get block deal data from exchanges.

        Args:
            days: Number of days to look back for block deals

        Returns:
            List of dictionaries containing block deal information
        """
        try:
            # In a real implementation, this would fetch from:
            # - NSE/BSE block deal windows (typically 30-minute window)
            # - Financial data APIs
            # - Exchange filings

            # Simulate block deals data (larger transactions than bulk deals)
            block_deals = [
                {
                    "date": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
                    "ticker": "HDFCBANK.NS",
                    "company_name": "HDFC Bank Limited",
                    "buyer_seller": "Buyer",
                    "quantity": 5000000,
                    "price": 1418.75,
                    "value": 7093750000,  # Much larger value indicates block deal
                    "institution": "Foreign Institutional Investors",
                    "type": "Block Deal",
                    "window": "10:30-11:00 AM"  # Block deal window
                },
                {
                    "date": (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d"),
                    "ticker": "ICICIBANK.NS",
                    "company_name": "ICICI Bank Limited",
                    "buyer_seller": "Seller",
                    "quantity": 3500000,
                    "price": 885.25,
                    "value": 3098375000,
                    "institution": "Domestic Mutual Funds",
                    "type": "Block Deal",
                    "window": "10:30-11:00 AM"
                }
            ]

            # Filter by date range
            cutoff_date = datetime.now() - timedelta(days=days)
            filtered_deals = [
                deal for deal in block_deals
                if datetime.strptime(deal["date"], "%Y-%m-%d") >= cutoff_date
            ]

            return filtered_deals

        except Exception as e:
            raise VendorUnavailableError(f"Failed to fetch block deals data: {str(e)}")

    def get_mutual_fund_flows(self, days: int = 30) -> Dict[str, any]:
        """Get mutual fund inflow/outflow data.

        Args:
            days: Number of days to look back for mutual fund flows

        Returns:
            Dictionary containing mutual fund flow analysis
        """
        try:
            # In a real implementation, this would fetch from:
            # - AMFI (Association of Mutual Funds in India) data
            # - Mutual fund houses' monthly reports
            # - Financial data APIs tracking MF investments

            # Simulate mutual fund flows data
            mf_flows = {
                "net_inflow": 15420.50,  # In Crores INR
                "equity_inflow": 8950.75,
                "debt_inflow": 4560.25,
                "hybrid_inflow": 1909.50,
                "total_aum": 425000.00,  # Total Assets Under Management in Crores
                "equity_aum": 185000.00,
                "debt_aum": 160000.00,
                "hybrid_aum": 80000.00,
                "top_sectors_inflow": [
                    {"sector": "Banking", "inflow": 2450.75},
                    {"sector": "IT", "inflow": 1890.50},
                    {"sector": "Pharma", "inflow": 1250.25},
                    {"sector": "Auto", "inflow": 980.00},
                    {"sector": "FMCG", "inflow": 820.50}
                ],
                "top_fund_categories_inflow": [
                    {"category": "Large Cap", "inflow": 3200.50},
                    {"category": "Flexi Cap", "inflow": 2150.25},
                    {"category": "Banking", "inflow": 1890.75},
                    {"category": "IT", "inflow": 1550.00}
                ],
                "trend": "bullish" if 15420.50 > 0 else "bearish",
                "consecutive_months_inflow": 4,
                "latest_update": datetime.now().strftime("%Y-%m-%d"),
                "data_source": "simulated"  # Would be "amfi", "value_research", etc. in real implementation
            }

            return mf_flows

        except Exception as e:
            raise VendorUnavailableError(f"Failed to fetch mutual fund flows data: {str(e)}")

    def get_institutional_sentiment(self) -> Dict[str, any]:
        """Get overall institutional sentiment based on multiple flow indicators.

        Returns:
            Dictionary containing institutional sentiment analysis
        """
        try:
            # Get all institutional flow data
            fii_dii = self.get_fii_dii_data()
            bulk_deals = self.get_bulk_deals_data(days=3)
            block_deals = self.get_block_deals_data(days=3)
            mf_flows = self.get_mutual_fund_flows(days=30)

            # Calculate sentiment scores
            fii_dii_score = 0
            if fii_dii["fii_net_buy"] > 0 and fii_dii["dii_net_buy"] > 0:
                fii_dii_score = 2  # Both FII and DII buying
            elif fii_dii["fii_net_buy"] > 0 or fii_dii["dii_net_buy"] > 0:
                fii_dii_score = 1  # One of them buying
            elif fii_dii["fii_net_buy"] < 0 and fii_dii["dii_net_buy"] < 0:
                fii_dii_score = -2  # Both selling
            elif fii_dii["fii_net_buy"] < 0 or fii_dii["dii_net_buy"] < 0:
                fii_dii_score = -1  # One of them selling

            # Analyze bulk/block deals
            deal_score = 0
            total_buy_value = 0
            total_sell_value = 0

            for deal in bulk_deals + block_deals:
                if deal["buyer_seller"] == "Buyer":
                    total_buy_value += deal["value"]
                else:
                    total_sell_value += deal["value"]

            if total_buy_value > total_sell_value * 1.5:
                deal_score = 2  # Strong buying
            elif total_buy_value > total_sell_value:
                deal_score = 1  # Mild buying
            elif total_sell_value > total_buy_value * 1.5:
                deal_score = -2  # Strong selling
            elif total_sell_value > total_buy_value:
                deal_score = -1  # Mild selling

            # Mutual fund sentiment
            mf_score = 0
            if mf_flows["net_inflow"] > 10000:  # Strong inflow
                mf_score = 2
            elif mf_flows["net_inflow"] > 0:  # Mild inflow
                mf_score = 1
            elif mf_flows["net_inflow"] < -10000:  # Strong outflow
                mf_score = -2
            elif mf_flows["net_inflow"] < 0:  # Mild outflow
                mf_score = -1

            # Calculate overall sentiment
            total_score = fii_dii_score + deal_score + mf_score

            if total_score >= 3:
                sentiment = "Very Bullish"
                confidence = min(90, 60 + total_score * 5)
            elif total_score >= 1:
                sentiment = "Bullish"
                confidence = min(75, 50 + total_score * 4)
            elif total_score <= -3:
                sentiment = "Very Bearish"
                confidence = min(90, 60 + abs(total_score) * 5)
            elif total_score <= -1:
                sentiment = "Bearish"
                confidence = min(70, 40 + abs(total_score) * 4)
            else:
                sentiment = "Neutral"
                confidence = 50

            return {
                "sentiment": sentiment,
                "confidence": confidence,
                "total_score": total_score,
                "components": {
                    "fii_dii": {
                        "score": fii_dii_score,
                        "data": fii_dii
                    },
                    "deals": {
                        "score": deal_score,
                        "bulk_deals": bulk_deals,
                        "block_deals": block_deals
                    },
                    "mutual_funds": {
                        "score": mf_score,
                        "data": mf_flows
                    }
                },
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            raise VendorUnavailableError(f"Failed to calculate institutional sentiment: {str(e)}")


# Global institutional flow analyzer instance
institutional_flow_analyzer = InstitutionalFlowAnalyzer()