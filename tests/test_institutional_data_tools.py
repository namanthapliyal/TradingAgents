"""Unit tests for institutional metrics tools: peer comparison, analyst consensus, and technical consensus."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd

from tradingagents.dataflows.vendors.analyst_consensus import get_analyst_consensus
from tradingagents.dataflows.vendors.peer_analysis import get_peer_comparison
from tradingagents.dataflows.vendors.technical_consensus import compute_technical_consensus


class TestInstitutionalDataTools:
    def test_peer_comparison_indian_mock(self):
        html_page = """
        <div id="company-info" data-warehouse-id="99999"></div>
        """
        html_peers = """
        <table class="data-table">
            <tr><th>S.No.</th><th>Company</th><th>CMPRs.</th><th>P/E</th><th>Mar CapRs.Cr.</th><th>Div Yld%</th><th>ROCE%</th></tr>
            <tr><td>1.</td><td>Competitor A</td><td>500.0</td><td>15.2</td><td>50000.0</td><td>1.5</td><td>18.5</td></tr>
            <tr><td>2.</td><td>Competitor B</td><td>120.0</td><td>25.0</td><td>20000.0</td><td>0.0</td><td>12.0</td></tr>
        </table>
        """
        mock_resp_page = MagicMock(status_code=200, content=html_page.encode("utf-8"))
        mock_resp_peers = MagicMock(status_code=200, content=html_peers.encode("utf-8"))

        with patch("requests.get", side_effect=[mock_resp_page, mock_resp_peers]):
            res = get_peer_comparison("TESTCO")
            assert "Sector Peer Comparison for TESTCO" in res
            assert "Competitor A" in res
            assert "Competitor B" in res
            assert "CMP(₹)" in res

    def test_analyst_consensus_mock(self):
        mock_info = {
            "currentPrice": 100.0,
            "targetMeanPrice": 140.0,
            "targetLowPrice": 110.0,
            "targetHighPrice": 160.0,
            "targetMedianPrice": 135.0,
            "recommendationKey": "buy",
            "numberOfAnalystOpinions": 20,
        }
        mock_recs = pd.DataFrame(
            [{"period": "0m", "strongBuy": 5, "buy": 10, "hold": 4, "sell": 1, "strongSell": 0}]
        )
        mock_ticker = MagicMock(info=mock_info, recommendations=mock_recs)
        mock_ticker.fast_info = MagicMock(last_price=100.0)

        with patch("yfinance.Ticker", return_value=mock_ticker):
            res = get_analyst_consensus("TEST")
            assert "BUY" in res
            assert "20 institutional broker research desks" in res
            assert "+40.0%" in res
            assert "Target Price Range" in res
            assert "Recent Months" in res

    def test_technical_consensus_mock(self):
        # Generate dummy 100 bars OHLCV
        dates = pd.date_range("2026-01-01", periods=100)
        df = pd.DataFrame(
            {
                "Date": dates,
                "Open": [100.0 + i for i in range(100)],
                "High": [105.0 + i for i in range(100)],
                "Low": [95.0 + i for i in range(100)],
                "Close": [102.0 + i for i in range(100)],
                "Volume": [100000] * 100,
            }
        )

        with patch(
            "tradingagents.dataflows.vendors.technical_consensus.load_ohlcv", return_value=df
        ):
            res = compute_technical_consensus("TEST", "2026-04-10")
            assert "Technical Consensus Matrix for TEST" in res
            assert "Overall Consensus Verdict" in res
            assert "Moving Averages Summary" in res
            assert "Oscillators Summary" in res

    def test_tools_present_in_analysts(self):
        from tradingagents.agents.analysts.fundamentals_analyst import TOOLS as FUND_TOOLS
        from tradingagents.agents.analysts.market_analyst import TOOLS as MKT_TOOLS
        from tradingagents.agents.analysts.news_analyst import TOOLS as NEWS_TOOLS

        fund_tool_names = [t.name for t in FUND_TOOLS]
        mkt_tool_names = [t.name for t in MKT_TOOLS]
        news_tool_names = [t.name for t in NEWS_TOOLS]

        assert "get_peer_comparison" in fund_tool_names
        assert "get_institutional_flow" in fund_tool_names
        assert "get_analyst_consensus" in fund_tool_names
        assert "get_technical_consensus" in mkt_tool_names
        assert "get_institutional_flow" in news_tool_names
        assert "get_analyst_consensus" in news_tool_names

    def test_institutional_flow_mock(self):
        from tradingagents.dataflows.vendors.institutional_flow import get_institutional_flow

        html_sh = """
        <section id="shareholding">
            <table class="data-table">
                <tr><th></th><th>Jun 2026</th><th>Sep 2026</th></tr>
                <tr><td>Promoters</td><td>50.0%</td><td>50.0%</td></tr>
                <tr><td>FIIs</td><td>20.0%</td><td>18.0%</td></tr>
                <tr><td>DIIs</td><td>15.0%</td><td>17.0%</td></tr>
            </table>
        </section>
        """
        mock_resp = MagicMock(status_code=200, content=html_sh.encode("utf-8"))
        with patch("requests.get", return_value=mock_resp):
            res = get_institutional_flow("RELIANCE")
            assert "Institutional Flow & Shareholding Analysis for RELIANCE" in res
            assert "FIIs" in res
            assert "DIIs" in res
            assert "Trimming / Selling (-)" in res
            assert "Accumulating (+)" in res
