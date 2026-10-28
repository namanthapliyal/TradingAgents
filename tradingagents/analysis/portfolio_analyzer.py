"""Indian Stock Portfolio Analysis Engine.

Performs comprehensive portfolio profile evaluations for Indian equities:
1. Real-time market pricing & P&L calculations.
2. In-depth fundamental analysis (P/E, Industry P/E, EBITDA, Net Profit, ROCE, ROE).
3. Live Indian financial news extraction & sentiment scoring.
4. Sectoral & thematic concentration / skew diagnostics (HHI metric).
5. Best vs. worst performers ranking.
6. Actionable recommendations (Hold / Buy / Sell) with data-backed rationale.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from tradingagents.dataflows.vendors.indian_news import evaluate_stock_sentiment, fetch_indian_news
from tradingagents.dataflows.vendors.screener_in.fundamentals import get_fundamentals_dict

logger = logging.getLogger(__name__)

# Indian sector benchmark average P/E multiples (Trailing Twelve Months)
SECTOR_BENCHMARK_PE = {
    "information technology": 25.0,
    "it": 25.0,
    "financial services": 16.0,
    "banking": 15.0,
    "finance": 16.5,
    "energy": 14.0,
    "oil & gas": 13.5,
    "fmcg": 42.0,
    "consumer goods": 40.0,
    "automobile": 23.0,
    "auto": 23.0,
    "healthcare": 32.0,
    "pharmaceuticals": 30.0,
    "pharma": 30.0,
    "metals & mining": 12.0,
    "metals": 12.0,
    "capital goods": 42.0,
    "infrastructure": 20.0,
    "power": 18.0,
    "telecom": 28.0,
    "chemicals": 27.0,
}


@dataclass
class HoldingItem:
    ticker: str
    quantity: float
    buy_price: float
    company_name: str = ""
    current_price: float = 0.0
    invested_value: float = 0.0
    current_value: float = 0.0
    unrealized_pnl: float = 0.0
    pnl_percent: float = 0.0
    portfolio_weight: float = 0.0
    sector: str = "Unknown"
    industry: str = "Unknown"
    stock_pe: float | None = None
    industry_pe: float | None = None
    pe_vs_industry: str | None = None  # "Premium", "Discount", "Fair"
    market_cap_cr: float | None = None
    ebitda_cr: float | None = None
    opm_percent: float | None = None
    net_profit_cr: float | None = None
    roce: float | None = None
    roe: float | None = None
    dividend_yield: float | None = None
    book_value: float | None = None
    sentiment_score: float = 5.0
    sentiment_label: str = "Neutral"
    news_catalysts: list[str] = field(default_factory=list)
    news_risks: list[str] = field(default_factory=list)
    recommendation: str = "HOLD"
    decision_reason: str = ""


class PortfolioAnalyzer:
    """Evaluates an Indian stock portfolio across fundamentals, sentiment, and risk concentration."""

    def __init__(self, cash: float = 0.0):
        self.cash = cash

    def _normalize_ticker(self, ticker: str) -> str:
        return ticker.upper().replace(".NS", "").replace(".BO", "").strip()

    def _get_benchmark_industry_pe(self, sector: str) -> float:
        sec_lower = sector.lower()
        for key, pe in SECTOR_BENCHMARK_PE.items():
            if key in sec_lower:
                return pe
        return 22.0  # Nifty broad market median P/E default

    def analyze_holding(self, item: dict[str, Any]) -> HoldingItem:
        raw_ticker = item.get("ticker", "")
        clean_ticker = self._normalize_ticker(raw_ticker)
        qty = float(item.get("quantity", 0))
        buy_price = float(item.get("buy_price", item.get("average_price", 0)))

        holding = HoldingItem(
            ticker=clean_ticker,
            quantity=qty,
            buy_price=buy_price,
            invested_value=qty * buy_price,
        )

        # 1. Fetch Fundamentals via Screener.in
        try:
            fund_data = get_fundamentals_dict(clean_ticker)
            holding.company_name = fund_data.get("company_name", clean_ticker)
            price = float(fund_data.get("current_price", 0.0))
            if price > 0:
                holding.current_price = price
            else:
                holding.current_price = buy_price

            holding.stock_pe = fund_data.get("stock_p_e") or fund_data.get("pe_ratio")
            holding.roce = fund_data.get("roce")
            holding.roe = fund_data.get("roe")
            holding.market_cap_cr = fund_data.get("market_cap")
            holding.book_value = fund_data.get("book_value")
            holding.dividend_yield = fund_data.get("dividend_yield")
            holding.sector = fund_data.get("sector") or "Diversified"
            holding.industry = fund_data.get("industry") or holding.sector
            holding.ebitda_cr = fund_data.get("ebitda_cr")
            holding.opm_percent = fund_data.get("opm_percent")
            holding.net_profit_cr = fund_data.get("net_profit_cr")

        except Exception as exc:
            logger.warning("Could not fetch screener fundamentals for %s: %s", clean_ticker, exc)
            holding.company_name = clean_ticker
            holding.current_price = buy_price

        # 2. Derive Industry P/E & Relative Valuation
        holding.industry_pe = self._get_benchmark_industry_pe(holding.sector)
        if holding.stock_pe and holding.industry_pe:
            ratio = holding.stock_pe / holding.industry_pe
            if ratio > 1.25:
                holding.pe_vs_industry = f"Premium ({ratio:.1f}x Industry)"
            elif ratio < 0.85:
                holding.pe_vs_industry = f"Discount ({ratio:.1f}x Industry)"
            else:
                holding.pe_vs_industry = f"Fair ({ratio:.1f}x Industry)"

        # 3. Calculate Returns
        holding.current_value = holding.quantity * holding.current_price
        holding.unrealized_pnl = holding.current_value - holding.invested_value
        if holding.invested_value > 0:
            holding.pnl_percent = round((holding.unrealized_pnl / holding.invested_value) * 100, 2)
        else:
            holding.pnl_percent = 0.0

        # 4. Fetch Real-time News & Sentiment
        try:
            news_items = fetch_indian_news(clean_ticker, limit=6)
            sent_eval = evaluate_stock_sentiment(news_items)
            holding.sentiment_score = sent_eval["score"]
            holding.sentiment_label = sent_eval["sentiment_label"]
            holding.news_catalysts = sent_eval["catalysts"]
            holding.news_risks = sent_eval["risks"]
        except Exception as exc:
            logger.warning("Could not fetch news/sentiment for %s: %s", clean_ticker, exc)

        return holding

    def evaluate_portfolio(self, raw_holdings: list[dict[str, Any]]) -> dict[str, Any]:
        """Process complete portfolio, calculate concentration, and synthesize decisions."""
        analyzed_holdings: list[HoldingItem] = []
        for h in raw_holdings:
            analyzed_holdings.append(self.analyze_holding(h))

        total_invested = sum(h.invested_value for h in analyzed_holdings)
        total_current_value = sum(h.current_value for h in analyzed_holdings)
        total_unrealized_pnl = total_current_value - total_invested
        total_pnl_percent = (
            round((total_unrealized_pnl / total_invested) * 100, 2) if total_invested > 0 else 0.0
        )

        # Calculate weights
        for h in analyzed_holdings:
            h.portfolio_weight = (
                round((h.current_value / total_current_value) * 100, 2)
                if total_current_value > 0
                else 0.0
            )

        # Sectoral distribution & concentration skew
        sector_distribution: dict[str, dict[str, Any]] = {}
        for h in analyzed_holdings:
            sec = h.sector
            if sec not in sector_distribution:
                sector_distribution[sec] = {
                    "total_value": 0.0,
                    "weight_percent": 0.0,
                    "stocks": [],
                }
            sector_distribution[sec]["total_value"] += h.current_value
            sector_distribution[sec]["stocks"].append(h.ticker)

        # HHI index calculation
        hhi = 0.0
        for data in sector_distribution.values():
            wt = (
                round((data["total_value"] / total_current_value) * 100, 2)
                if total_current_value > 0
                else 0.0
            )
            data["weight_percent"] = wt
            hhi += wt**2

        if hhi > 2500:
            skew_status = "High Concentration (Significant Sector Skew)"
            skew_risk = "CRITICAL"
        elif hhi > 1500:
            skew_status = "Moderate Concentration (Acceptable with vigilance)"
            skew_risk = "MODERATE"
        else:
            skew_status = "Well-Diversified Portfolio"
            skew_risk = "LOW"

        # Generate Hold / Buy / Sell decisions
        for h in analyzed_holdings:
            reasons = []
            rec = "HOLD"

            # 1. Fundamental Quality
            strong_fundamentals = (h.roce and h.roce >= 15.0) or (h.roe and h.roe >= 15.0)
            weak_fundamentals = (h.roce and h.roce < 8.0) or (h.roe and h.roe < 8.0)

            # 2. Valuation
            expensive_pe = h.stock_pe and h.industry_pe and (h.stock_pe > 1.35 * h.industry_pe)
            attractive_pe = h.stock_pe and h.industry_pe and (h.stock_pe < 0.90 * h.industry_pe)

            # 3. Performance & Momentum
            deep_loss = h.pnl_percent < -15.0
            massive_gain = h.pnl_percent > 40.0
            positive_momentum = h.pnl_percent > 5.0

            # 4. Sector concentration penalty
            sec_weight = sector_distribution.get(h.sector, {}).get("weight_percent", 0.0)
            overweight_sector = sec_weight > 30.0

            if (
                strong_fundamentals
                and (attractive_pe or positive_momentum)
                and h.sentiment_score >= 5.0
            ):
                rec = "BUY / ACCUMULATE"
                reasons.append(
                    f"Robust fundamentals (ROCE: {h.roce}%) trading at an attractive valuation "
                    f"relative to industry P/E ({h.stock_pe:.1f} vs {h.industry_pe:.1f})."
                )
            elif massive_gain and (expensive_pe or overweight_sector):
                rec = "SELL (PROFIT BOOKING)"
                reasons.append(
                    f"Strong realized gains (+{h.pnl_percent}%); valuation is stretched "
                    f"(P/E {h.stock_pe:.1f} vs Industry {h.industry_pe:.1f}) and sector weight "
                    f"is concentrated ({sec_weight:.1f}%)."
                )
            elif deep_loss and weak_fundamentals:
                rec = "SELL (EXIT / REBALANCE)"
                reasons.append(
                    f"Underperforming asset ({h.pnl_percent}%) with weak return on capital "
                    f"(ROCE {h.roce}%). Reallocate to higher-conviction opportunities."
                )
            elif weak_fundamentals and expensive_pe:
                rec = "SELL"
                reasons.append(
                    "Sub-par capital efficiency coupled with demanding valuation multiples."
                )
            elif h.sentiment_score <= 3.0:
                rec = "REDUCE / CAUTION"
                reasons.append(
                    f"Adverse news flow and bearish financial sentiment ({h.sentiment_score}/10)."
                )
            else:
                rec = "HOLD"
                reasons.append(
                    f"Stable business performance; fair valuation (P/E {h.stock_pe or 'N/A'}); "
                    f"neutral risk-reward at current levels."
                )

            h.recommendation = rec
            h.decision_reason = " ".join(reasons)

        # Rank Best and Worst performers
        sorted_by_performance = sorted(analyzed_holdings, key=lambda x: x.pnl_percent, reverse=True)
        best_performers = sorted_by_performance[:3]
        worst_performers = sorted_by_performance[-3:][::-1]

        return {
            "summary": {
                "total_invested": round(total_invested, 2),
                "total_current_value": round(total_current_value, 2),
                "total_unrealized_pnl": round(total_unrealized_pnl, 2),
                "total_pnl_percent": total_pnl_percent,
                "cash_available": self.cash,
                "total_portfolio_wealth": round(total_current_value + self.cash, 2),
                "holdings_count": len(analyzed_holdings),
                "hhi_index": round(hhi, 1),
                "skew_status": skew_status,
                "skew_risk": skew_risk,
                "evaluated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            "holdings": analyzed_holdings,
            "sector_distribution": sector_distribution,
            "best_performers": best_performers,
            "worst_performers": worst_performers,
        }

    def format_markdown_report(self, results: dict[str, Any]) -> str:
        """Render a clean, rich Markdown report summarizing the portfolio analysis."""
        s = results["summary"]
        holdings: list[HoldingItem] = results["holdings"]
        sectors = results["sector_distribution"]

        lines = [
            "# 🇮🇳 Indian Stock Portfolio Health & Strategy Report",
            f"**Evaluation Date:** {s['evaluated_at']} | **Total Holdings:** {s['holdings_count']}",
            "",
            "## 1. Portfolio Financial Overview",
            f"- **Invested Capital:** ₹{s['total_invested']:,.2f}",
            f"- **Current Market Value:** ₹{s['total_current_value']:,.2f}",
            f"- **Unrealized P&L:** ₹{s['total_unrealized_pnl']:,.2f} ({'+' if s['total_pnl_percent'] >= 0 else ''}{s['total_pnl_percent']}%)",
            f"- **Free Cash:** ₹{s['cash_available']:,.2f}",
            f"- **Total Wealth:** ₹{s['total_portfolio_wealth']:,.2f}",
            "",
            "---",
            "## 2. Sectoral Allocation & Thematic Concentration",
            f"- **Herfindahl-Hirschman Index (HHI):** `{s['hhi_index']}` — **{s['skew_status']}** (Risk Level: `{s['skew_risk']}`)",
            "",
            "| Sector | Current Value (₹) | Portfolio Weight | Exposure Risk | Stocks |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]

        for sec, data in sorted(
            sectors.items(), key=lambda x: x[1]["weight_percent"], reverse=True
        ):
            wt = data["weight_percent"]
            risk = "⚠️ Overconcentrated (>25%)" if wt > 25.0 else "✅ Balanced (<25%)"
            stocks_str = ", ".join(data["stocks"])
            lines.append(
                f"| {sec} | ₹{data['total_value']:,.2f} | {wt:.1f}% | {risk} | {stocks_str} |"
            )

        lines.extend(
            [
                "",
                "---",
                "## 3. Stock-by-Stock Fundamentals & Sentiment Matrix",
                "",
                "| Stock | Weight | P&L % | Current Price | Stock P/E | Industry P/E | ROCE | EBITDA (Cr) | Sentiment |",
                "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
            ]
        )

        for h in holdings:
            pe_str = f"{h.stock_pe:.1f}" if h.stock_pe else "N/A"
            ind_pe_str = f"{h.industry_pe:.1f}" if h.industry_pe else "N/A"
            roce_str = f"{h.roce:.1f}%" if h.roce else "N/A"
            ebitda_str = f"₹{h.ebitda_cr:,.0f}" if h.ebitda_cr else "N/A"
            pnl_sign = "+" if h.pnl_percent >= 0 else ""
            lines.append(
                f"| **{h.ticker}** | {h.portfolio_weight:.1f}% | {pnl_sign}{h.pnl_percent:.1f}% | ₹{h.current_price:,.2f} | {pe_str} | {ind_pe_str} | {roce_str} | {ebitda_str} | {h.sentiment_label} ({h.sentiment_score}/10) |"
            )

        lines.extend(
            [
                "",
                "---",
                "## 4. Best & Worst Performers",
                "",
                "### 🟢 Best Performing Stocks",
            ]
        )
        for b in results["best_performers"]:
            pnl_label = "Gain" if b.unrealized_pnl >= 0 else "Loss"
            pnl_sign = "+" if b.pnl_percent > 0 else ""
            lines.append(
                f"- **{b.ticker}** ({b.company_name}): **{pnl_sign}{b.pnl_percent:.2f}%** return ({pnl_label}: ₹{abs(b.unrealized_pnl):,.2f}) — Weight: {b.portfolio_weight:.1f}%"
            )

        lines.extend(
            [
                "",
                "### 🔴 Worst Performing Stocks",
            ]
        )
        for w in results["worst_performers"]:
            pnl_label = "Gain" if w.unrealized_pnl >= 0 else "Loss"
            pnl_sign = "+" if w.pnl_percent >= 0 else ""
            lines.append(
                f"- **{w.ticker}** ({w.company_name}): **{pnl_sign}{w.pnl_percent:.2f}%** return ({pnl_label}: ₹{abs(w.unrealized_pnl):,.2f}) — Weight: {w.portfolio_weight:.1f}%"
            )

        lines.extend(
            [
                "",
                "---",
                "## 5. Strategic Recommendations: Hold, Buy, or Sell",
                "",
                "| Stock | Recommendation | Key Decision Rationale | Recent News Catalyst / Risk |",
                "| :--- | :--- | :--- | :--- |",
            ]
        )

        for h in holdings:
            news_headline = (
                h.news_catalysts[0]
                if h.news_catalysts
                else (h.news_risks[0] if h.news_risks else "Stable market coverage")
            )
            # truncate long headlines
            if len(news_headline) > 75:
                news_headline = news_headline[:72] + "..."
            lines.append(
                f"| **{h.ticker}** | **{h.recommendation}** | {h.decision_reason} | *{news_headline}* |"
            )

        return "\n".join(lines)


def main():
    import argparse
    import csv
    import json
    import os
    import sys

    # Reconfigure stdout for Windows console UTF-8 support
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Indian Equity Portfolio Health, Fundamentals & Sentiment Analyzer"
    )
    parser.add_argument(
        "--portfolio",
        "-p",
        help="Path to portfolio JSON or CSV file",
        default=None,
    )
    parser.add_argument(
        "--holdings",
        help="Comma-separated ticker:quantity:buy_price (e.g. 'RELIANCE:100:1050,TCS:50:2200')",
        default=None,
    )
    parser.add_argument(
        "--cash",
        "-c",
        type=float,
        default=0.0,
        help="Free cash available in INR",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Save markdown analysis report to this file",
        default=None,
    )

    args = parser.parse_args()
    holdings_list = []

    if args.portfolio:
        p_path = args.portfolio
        if not os.path.exists(p_path):
            print(f"Error: Portfolio file not found: {p_path}", file=sys.stderr)
            sys.exit(1)

        if p_path.endswith(".json"):
            with open(p_path, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "positions" in data:
                    holdings_list = data["positions"]
                    if "cash" in data and args.cash == 0.0:
                        args.cash = float(data["cash"])
                elif isinstance(data, list):
                    holdings_list = data
        elif p_path.endswith(".csv"):
            with open(p_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    holdings_list.append(
                        {
                            "ticker": r.get("ticker") or r.get("symbol") or r.get("Stock", ""),
                            "quantity": float(
                                r.get("quantity") or r.get("qty") or r.get("Shares", 0)
                            ),
                            "buy_price": float(
                                r.get("buy_price") or r.get("average_price") or r.get("Price", 0)
                            ),
                        }
                    )
    elif args.holdings:
        for item in args.holdings.split(","):
            parts = item.strip().split(":")
            if len(parts) >= 3:
                holdings_list.append(
                    {
                        "ticker": parts[0].strip(),
                        "quantity": float(parts[1].strip()),
                        "buy_price": float(parts[2].strip()),
                    }
                )
    else:
        # Demo portfolio if no args provided
        print(
            "No portfolio input provided. Demonstrating with representative Indian portfolio...\n"
        )
        holdings_list = [
            {"ticker": "RELIANCE", "quantity": 100, "buy_price": 1050.0},
            {"ticker": "TCS", "quantity": 50, "buy_price": 2200.0},
            {"ticker": "HDFCBANK", "quantity": 150, "buy_price": 650.0},
            {"ticker": "INFY", "quantity": 80, "buy_price": 1500.0},
            {"ticker": "TATAMOTORS", "quantity": 120, "buy_price": 720.0},
            {"ticker": "ITC", "quantity": 200, "buy_price": 425.0},
        ]
        args.cash = 100000.0

    analyzer = PortfolioAnalyzer(cash=args.cash)
    print(
        f"Evaluating {len(holdings_list)} Indian portfolio holdings (Screener.in fundamentals + Indian news)..."
    )
    results = analyzer.evaluate_portfolio(holdings_list)
    markdown_report = analyzer.format_markdown_report(results)

    print("\n" + markdown_report)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(markdown_report)
        print(f"\n[+] Analysis saved to: {args.output}")


if __name__ == "__main__":
    main()
