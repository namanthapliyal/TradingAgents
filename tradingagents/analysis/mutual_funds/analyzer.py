from typing import Annotated, Dict, List, Optional
from datetime import datetime, timedelta
import requests
import pandas as pd

from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.net import vendor_reachable


class MutualFundAnalyzer:
    """Analyzes mutual funds including NAV tracking, expense ratios, and fund manager performance."""

    def __init__(self):
        self.name = "Mutual Fund Analyzer"

    def get_mutual_fund_nav(self, scheme_code: str) -> Dict[str, any]:
        """Get NAV (Net Asset Value) data for a mutual fund scheme.

        Args:
            scheme_code: Mutual fund scheme code

        Returns:
            Dictionary containing NAV information
        """
        try:
            # In a real implementation, this would fetch from:
            # - AMFI (Association of Mutual Funds in India) NAV API
            # - Mutual fund house websites
            # - Financial data APIs (Moneycontrol, Value Research, etc.)

            # For now, return simulated data
            # In production, this would be replaced with actual API calls

            # Simulate fetching NAV data
            nav_data = {
                "scheme_code": scheme_code,
                "scheme_name": "HDFC Top 100 Fund - Growth",
                "nav": 425.75,
                "nav_date": datetime.now().strftime("%Y-%m-%d"),
                "recalculated_nav": 425.75,  # For revised NAVs
                "change": 3.25,
                "change_percent": 0.77,
                "aum": 28500.50,  # In Crores INR
                "expense_ratio": 1.85,  # Annual expense ratio (%)
                "fund_manager": "Prashant Jain",
                "manager_tenure": "8 years 3 months",
                "minimum_investment": 100,  # Minimum lump sum in INR
                "minimum_sip": 500,  # Minimum SIP in INR
                "load_structure": "No Load",  # Entry/Exit load
                "risk_level": "Moderately High",
                "category": "Large Cap",
                "benchmark": "Nifty 100 TRI",
                "data_source": "simulated"  # Would be "amfi", "moneycontrol", etc. in real implementation
            }

            return nav_data

        except Exception as e:
            raise VendorUnavailableError(f"Failed to fetch mutual fund NAV: {str(e)}")

    def get_mutual_fund_historical_nav(self, scheme_code: str, days: int = 30) -> List[Dict[str, any]]:
        """Get historical NAV data for a mutual fund scheme.

        Args:
            scheme_code: Mutual fund scheme code
            days: Number of days of historical data to fetch

        Returns:
            List of dictionaries containing historical NAV data
        """
        try:
            # In a real implementation, this would fetch historical NAV from:
            # - AMFI historical NAV archives
            # - Mutual fund house websites
            # - Financial data APIs

            # Simulate historical NAV data
            historical_nav = []
            base_nav = 400.00

            for i in range(days):
                date = datetime.now() - timedelta(days=i)
                # Simulate some random walk for NAV
                daily_change = (hash(f"{scheme_code}{date.strftime('%Y%m%d')}") % 200 - 100) / 1000  # -0.1 to +0.1
                nav = base_nav * (1 + daily_change)
                base_nav = nav  # For compounding effect

                historical_nav.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "nav": round(nav, 2),
                    "scheme_code": scheme_code
                })

            # Return in chronological order (oldest first)
            return list(reversed(historical_nav))

        except Exception as e:
            raise VendorUnavailableError(f"Failed to fetch historical NAV: {str(e)}")

    def get_mutual_fund_returns(self, scheme_code: str) -> Dict[str, any]:
        """Get returns data for a mutual fund scheme across various periods.

        Args:
            scheme_code: Mutual fund scheme code

        Returns:
            Dictionary containing returns across different time periods
        """
        try:
            # In a real implementation, this would fetch returns data from:
            # - AMFI factsheets
            # - Mutual fund house websites
            # - Financial data APIs

            # Simulate returns data
            returns_data = {
                "scheme_code": scheme_code,
                "scheme_name": "HDFC Top 100 Fund - Growth",
                "returns": {
                    "1_year": 18.50,
                    "3_year": 14.25,
                    "5_year": 16.80,
                    "10_year": 15.40,
                    "since_inception": 18.90
                },
                "benchmark_returns": {
                    "1_year": 16.20,
                    "3_year": 12.80,
                    "5_year": 14.50,
                    "10_year": 13.20,
                    "since_inception": 16.50
                },
                "category_average": {
                    "1_year": 17.10,
                    "3_year": 13.50,
                    "5_year": 15.20,
                    "10_year": 14.00
                },
                "ranking": {
                    "1_year": 45,  # Percentile ranking
                    "3_year": 38,
                    "5_year": 42,
                    "10_year": 35
                },
                "data_source": "simulated"  # Would be "amfi", "moneycontrol", etc. in real implementation
            }

            return returns_data

        except Exception as e:
            raise VendorUnavailableError(f"Failed to fetch mutual fund returns: {str(e)}")

    def get_expense_ratio_analysis(self, scheme_code: str) -> Dict[str, any]:
        """Analyze expense ratio of a mutual fund scheme.

        Args:
            scheme_code: Mutual fund scheme code

        Returns:
            Dictionary containing expense ratio analysis
        """
        try:
            # Get NAV data which includes expense ratio
            nav_data = self.get_mutual_fund_nav(scheme_code)
            expense_ratio = nav_data.get("expense_ratio", 0)

            # Categorize expense ratio
            if expense_ratio <= 0.5:
                expense_category = "Very Low"
            elif expense_ratio <= 1.0:
                expense_category = "Low"
            elif expense_ratio <= 1.5:
                expense_category = "Moderate"
            elif expense_ratio <= 2.0:
                expense_category = "High"
            else:
                expense_category = "Very High"

            # Calculate impact on returns over time
            # Assuming 12% annual return before expenses
            assumed_return = 12.00
            net_return = assumed_return - expense_ratio

            return {
                "scheme_code": scheme_code,
                "expense_ratio": expense_ratio,
                "expense_category": expense_category,
                "assumed_gross_return": assumed_return,
                "estimated_net_return": net_return,
                "expense_impact_percent": (expense_ratio / assumed_return) * 100,
                "nav_data": nav_data,
                "data_source": nav_data.get("data_source", "simulated")
            }

        except Exception as e:
            raise VendorUnavailableError(f"Failed to analyze expense ratio: {str(e)}")

    def get_fund_manager_analysis(self, scheme_code: str) -> Dict[str, any]:
        """Analyze fund manager performance and tenure.

        Args:
            scheme_code: Mutual fund scheme code

        Returns:
            Dictionary containing fund manager analysis
        """
        try:
            # Get NAV data which includes fund manager info
            nav_data = self.get_mutual_fund_nav(scheme_code)
            fund_manager = nav_data.get("fund_manager", "Unknown")
            manager_tenure_str = nav_data.get("manager_tenure", "0 years")

            # Parse manager tenure (simplified)
            # In practice, would parse strings like "8 years 3 months"
            years_of_experience = 8  # Default simulated value
            if "years" in manager_tenure_str:
                try:
                    years_part = manager_tenure_str.split("years")[0].strip()
                    years_of_experience = float(years_part)
                except:
                    years_of_experience = 8

            # Get returns data for performance analysis
            returns_data = self.get_mutual_fund_returns(scheme_code)
            three_year_returns = returns_data.get("returns", {}).get("3_year", 0)
            five_year_returns = returns_data.get("returns", {}).get("5_year", 0)

            # Score fund manager (simplified scoring)
            manager_score = 0
            if years_of_experience >= 10:
                manager_score += 3
            elif years_of_experience >= 5:
                manager_score += 2
            elif years_of_experience >= 2:
                manager_score += 1

            if three_year_returns >= 15:
                manager_score += 3
            elif three_year_returns >= 10:
                manager_score += 2
            elif three_year_returns >= 5:
                manager_score += 1

            if five_year_returns >= 16:
                manager_score += 2
            elif five_year_returns >= 12:
                manager_score += 1

            # Categorize manager performance
            if manager_score >= 8:
                manager_rating = "Excellent"
            elif manager_score >= 6:
                manager_rating = "Good"
            elif manager_score >= 4:
                manager_rating = "Average"
            else:
                manager_rating = "Needs Improvement"

            return {
                "scheme_code": scheme_code,
                "fund_manager": fund_manager,
                "manager_tenure": manager_tenure_str,
                "years_of_experience": years_of_experience,
                "three_year_returns": three_year_returns,
                "five_year_returns": five_year_returns,
                "manager_score": manager_score,
                "manager_rating": manager_rating,
                "nav_data": nav_data,
                "returns_data": returns_data,
                "data_source": nav_data.get("data_source", "simulated")
            }

        except Exception as e:
            raise VendorUnavailableError(f"Failed to analyze fund manager: {str(e)}")

    def get_mutual_fund_risk_analysis(self, scheme_code: str) -> Dict[str, any]:
        """Analyze risk metrics of a mutual fund scheme.

        Args:
            scheme_code: Mutual fund scheme code

        Returns:
            Dictionary containing risk analysis
        """
        try:
            # Get NAV data
            nav_data = self.get_mutual_fund_nav(scheme_code)

            # In a real implementation, this would fetch:
            # - Standard deviation, beta, Sharpe ratio from factsheets
            # - Risk metrics from financial data APIs

            # Simulate risk analysis
            risk_analysis = {
                "scheme_code": scheme_code,
                "scheme_name": nav_data.get("scheme_name", "Unknown"),
                "standard_deviation": 18.50,  # Annualized
                "beta": 1.12,  # vs benchmark
                "sharpe_ratio": 0.85,  # Risk-adjusted return
                "sortino_ratio": 1.10,  # Downside risk-adjusted
                "alpha": 2.30,  # vs benchmark
                "r_squared": 0.88,  # Correlation with benchmark
                "max_drawdown": -18.25,  # Maximum peak-to-trough decline
                "risk_category": "Moderately High",
                "nav_data": nav_data,
                "data_source": "simulated"  # Would be "amfi", "moneycontrol", etc. in real implementation
            }

            return risk_analysis

        except Exception as e:
            raise VendorUnavailableError(f"Failed to analyze mutual fund risk: {str(e)}")

    def compare_mutual_funds(self, scheme_codes: List[str]) -> Dict[str, any]:
        """Compare multiple mutual fund schemes.

        Args:
            scheme_codes: List of mutual fund scheme codes to compare

        Returns:
            Dictionary containing comparison analysis
        """
        try:
            comparison_data = {
                "schemes": {},
                "comparison_metrics": [
                    "nav", "expense_ratio", "returns_1_year", "returns_3_year",
                    "returns_5_year", "sharpe_ratio", "expense_category"
                ],
                "timestamp": datetime.now().isoformat()
            }

            for scheme_code in scheme_codes:
                try:
                    # Get basic info
                    nav_data = self.get_mutual_fund_nav(scheme_code)
                    returns_data = self.get_mutual_fund_returns(scheme_code)
                    expense_analysis = self.get_expense_ratio_analysis(scheme_code)
                    risk_analysis = self.get_mutual_fund_risk_analysis(scheme_code)

                    comparison_data["schemes"][scheme_code] = {
                        "scheme_name": nav_data.get("scheme_name", "Unknown"),
                        "nav": nav_data.get("nav", 0),
                        "expense_ratio": nav_data.get("expense_ratio", 0),
                        "expense_category": expense_analysis.get("expense_category", "Unknown"),
                        "returns_1_year": returns_data.get("returns", {}).get("1_year", 0),
                        "returns_3_year": returns_data.get("returns", {}).get("3_year", 0),
                        "returns_5_year": returns_data.get("returns", {}).get("5_year", 0),
                        "sharpe_ratio": risk_analysis.get("sharpe_ratio", 0),
                        "risk_category": risk_analysis.get("risk_category", "Unknown"),
                        "fund_manager": nav_data.get("fund_manager", "Unknown")
                    }

                except VendorUnavailableError:
                    # Skip schemes that can't be fetched
                    continue
                except Exception:
                    # Skip schemes with other errors
                    continue

            # Add ranking if we have multiple schemes
            if len(comparison_data["schemes"]) > 1:
                # Rank by 3-year returns (descending)
                sorted_schemes = sorted(
                    comparison_data["schemes"].items(),
                    key=lambda x: x[1].get("returns_3_year", 0),
                    reverse=True
                )
                comparison_data["ranking_by_3year_returns"] = [
                    {"scheme_code": code, "rank": idx + 1}
                    for idx, (code, _) in enumerate(sorted_schemes)
                ]

            return comparison_data

        except Exception as e:
            raise VendorUnavailableError(f"Failed to compare mutual funds: {str(e)}")


# Global mutual fund analyzer instance
mutual_fund_analyzer = MutualFundAnalyzer()