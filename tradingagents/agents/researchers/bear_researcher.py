from tradingagents.agents.context import (
    get_instrument_context_from_state,
    get_language_instruction,
    opponent_argument_or_opening,
    report_or_absent,
)


def create_bear_researcher(llm):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = opponent_argument_or_opening(
            investment_debate_state.get("current_response", ""), "bull analyst"
        )
        market_research_report = report_or_absent(state["market_report"], "market")
        sentiment_report = report_or_absent(state["sentiment_report"], "sentiment")
        news_report = report_or_absent(state["news_report"], "news")
        fundamentals_report = report_or_absent(state["fundamentals_report"], "fundamentals")
        instrument_context = get_instrument_context_from_state(state)
        asset_type = state.get("asset_type", "stock")
        if asset_type == "mutual_fund":
            target_label = "Indian mutual fund scheme"
            fundamentals_label = "Mutual Fund performance and AMFI details report"
            asset_risk_guidelines = (
                "- Fund Underperformance: Scrutinize trailing returns (1M, 6M, 1Y, 3Y, 5Y) for lag against category peers or benchmark index.\n"
                "- Cost & Inefficiencies: Highlight expense ratios, potential exit loads, AUM bloat, and fund manager turnover.\n"
                "- Market Exposure: Note that open-ended funds bear full market downside without cash hedging."
            )
        elif asset_type == "etf":
            target_label = "Indian exchange traded fund (ETF)"
            fundamentals_label = "ETF performance and benchmark report"
            asset_risk_guidelines = (
                "- ETF Limitations: Highlight tracking error, secondary market illiquidity, wide bid-ask spreads, and premium/discount dislocations.\n"
                "- Unhedged Index Risk: Note lack of active risk management during broad market drawdowns."
            )
        elif asset_type == "crypto":
            target_label = "crypto asset"
            fundamentals_label = "Asset fundamentals report (may be unavailable for crypto)"
            asset_risk_guidelines = "- Crypto Volatility: Highlight regulatory scrutiny, volatility, and lack of fundamental cash flows."
        else:
            target_label = "Indian equity stock"
            fundamentals_label = "Company fundamentals report"
            asset_risk_guidelines = (
                "- Valuation & Growth: Highlight elevated P/E vs industry, revenue slowdown, or EBITDA margin erosion.\n"
                "- Financial & Operational Risks: Emphasize debt levels, working capital cycles, corporate governance, and FII outflow headwinds."
            )

        prompt = f"""You are an institutional financial research analyst conducting fiduciary risk assessment. You are a Bear Analyst making the case against investing in the {target_label}. Your goal is to present a well-reasoned argument emphasizing risks, challenges, and negative indicators. Leverage the provided research and data to highlight potential downsides and counter bullish arguments effectively.

Key points to focus on:
{asset_risk_guidelines}
- Competitive Weaknesses: Emphasize vulnerabilities such as weaker market positioning, declining margins, or industry headwinds.
- Negative Indicators: Use evidence from financial data, market trends, or recent adverse news to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Present your argument directly and assertively, engaging with the bull analyst's points and debating effectively.

Resources available:

{instrument_context}
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
{fundamentals_label}: {fundamentals_report}
Conversation history of the debate: {history}
Last bull argument: {current_response}
Use this information to deliver a compelling bear argument, refute the bull's claims, and engage in a dynamic debate that demonstrates the risks and weaknesses of investing in the {target_label}.
""" + get_language_instruction()

        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        # Guard against safety refusals from small models
        if "cannot participate" in content.lower() or "as an ai" in content.lower():
            content = (
                f"The downside risk case for {target_label} is significant: "
                f"recent operating headwinds, valuation multiples lacking safety margin, "
                f"and macroeconomic and sector-level pressures indicate unfavorable risk-reward."
            )

        argument = f"Bear Analyst: {content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
