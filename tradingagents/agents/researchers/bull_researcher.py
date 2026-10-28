from tradingagents.agents.context import (
    get_instrument_context_from_state,
    get_language_instruction,
    opponent_argument_or_opening,
    report_or_absent,
)


def create_bull_researcher(llm):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = opponent_argument_or_opening(
            investment_debate_state.get("current_response", ""), "bear analyst"
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
            asset_guidelines = (
                "- Mutual Fund Compounding: Highlight historical CAGR outperformance across 1Y, 3Y, 5Y versus category benchmarks.\n"
                "- Fund Pedigree & Strategy: Emphasize AMC repute, disciplined portfolio management, and resilience in market downturns.\n"
                "- Systematic Accumulation: Frame investment in terms of systematic SIP compounding or strategic lumpsum allocation."
            )
        elif asset_type == "etf":
            target_label = "Indian exchange traded fund (ETF)"
            fundamentals_label = "ETF performance and benchmark report"
            asset_guidelines = (
                "- Benchmark Exposure: Highlight secular growth of the underlying index or commodity (e.g. Nifty 50, Bank Nifty, Gold).\n"
                "- Operational Efficiency: Emphasize low expense ratios, high secondary market trading liquidity, and absence of manager risk."
            )
        elif asset_type == "crypto":
            target_label = "crypto asset"
            fundamentals_label = "Asset fundamentals report (may be unavailable for crypto)"
            asset_guidelines = "- Crypto Momentum: Highlight network adoption, on-chain metrics, and liquidity trends."
        else:
            target_label = "Indian equity stock"
            fundamentals_label = "Company fundamentals report"
            asset_guidelines = (
                "- Growth Potential: Highlight market opportunities, revenue projections, EBITDA margins, and ROCE.\n"
                "- Competitive Advantages: Emphasize moats, market positioning, order books, and corporate governance."
            )

        prompt = f"""You are a Bull Analyst advocating for investing in the {target_label}. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

Key points to focus on:
{asset_guidelines}
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, addressing concerns thoroughly and showing why the bull perspective holds stronger merit.
- Engagement: Present your argument in a conversational style, engaging directly with the bear analyst's points and debating effectively rather than just listing data.

Resources available:
{instrument_context}
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
{fundamentals_label}: {fundamentals_report}
Conversation history of the debate: {history}
Last bear argument: {current_response}
Use this information to deliver a compelling bull argument, refute the bear's concerns, and engage in a dynamic debate that demonstrates the strengths of the bull position.
""" + get_language_instruction()

        response = llm.invoke(prompt)

        argument = f"Bull Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
