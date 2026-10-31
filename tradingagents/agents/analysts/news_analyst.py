from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.analysts.turn import take_turn
from tradingagents.agents.context import get_instrument_context_from_state, get_language_instruction
from tradingagents.agents.tools import (
    get_analyst_consensus,
    get_global_news,
    get_institutional_flow,
    get_macro_indicators,
    get_macro_snapshot,
    get_news,
    get_prediction_markets,
    search_market_news,
)

# The tools this analyst is offered; its tool node is built from the same tuple.
TOOLS = (
    get_news,
    get_global_news,
    get_institutional_flow,
    get_analyst_consensus,
    get_macro_indicators,
    get_macro_snapshot,
    search_market_news,
    get_prediction_markets,
)


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        asset_type = state.get("asset_type", "stock")
        asset_label = "company" if asset_type == "stock" else "asset"
        instrument_context = get_instrument_context_from_state(state)

        # Pre-fetch unified global macro and commodity regime (100% free)
        macro_snapshot = ""
        try:
            from tradingagents.agents.context import resolve_instrument_identity

            identity = resolve_instrument_identity(state.get("company_of_interest", ""))
            sector = identity.get("industry") or identity.get("sector") or ""
            macro_snapshot = get_macro_snapshot.func(as_of_date=current_date, sector=sector)
        except Exception:
            pass

        macro_section = (
            f"\n\n## Pre-Fetched Global Macroeconomic & Commodity Regime ({current_date}):\n"
            f"{macro_snapshot}\n\n"
            f"MANDATORY MACRO INSTRUCTION:\n"
            f"You MUST explicitly correlate the company's financial performance and recent stock price trends against the Macro Snapshot above.\n"
            f"Specifically evaluate:\n"
            f"- Realization prices for key commodities (e.g. Silver drop of -18.3%, Gold, Base Metals) as revenue and margin headwinds/tailwinds.\n"
            f"- Input energy costs (e.g. Brent Crude rise of +13.6%) as operating smelting/processing cost pressures.\n"
            f"- Global liquidity and currency dynamics (US Dollar Index DXY, US 10-Year Treasury Yields at 4.93%) driving FII equity flows and broad market risk sentiment.\n"
        ) if macro_snapshot else ""

        system_message = (
            f"You are a news researcher tasked with analyzing recent news and trends over the past week.\n\n"
            f"MANDATORY RULES:\n"
            f"1. You MUST call `get_news(start_date, end_date)` to retrieve the latest real news stories for the {asset_label} under analysis. "
            f"Base all corporate commentary, catalysts, and sentiment strictly on the retrieved articles. Do not invent fictitious headlines or events.\n"
            f"2. Use `get_global_news(curr_date, look_back_days, limit)` for broader macroeconomic developments.\n"
            f"3. Use `get_macro_indicators` to ground macro commentary in actual data from FRED (e.g. 'cpi', 'core_pce', 'unemployment', 'fed_funds_rate', '10y_treasury', 'yield_curve').\n"
            f"4. For Indian instruments (NSE/BSE stocks, Mutual Funds, ETFs): `get_news` retrieves Indian financial news coverage covering corporate earnings, SEBI updates, and sector events. Consider Indian domestic factors (RBI repo rate, Indian CPI inflation, FII/DII institutional flows, budget/tax policies) alongside global cues.\n"
            f"5. If `get_news` returns no articles or limited coverage, you MUST call `search_market_news(query, ticker)` (e.g. query='quarterly results earnings turnaround') to retrieve real-time stories from public search engines before concluding there is no news.\n"
            f"6. ALWAYS call `get_macro_snapshot(as_of_date, sector)` to assess the global macroeconomic regime (US 10-Year Treasury Yields, US Dollar Index DXY, LME Base Metals, Silver/Gold, Brent Crude Oil, VIX). For cyclical and commodity equities (e.g., metals & mining, utilities), explicitly evaluate how US bond yields and dollar strength act as headwinds or tailwinds on selling prices and margins.\n"
            f"{macro_section}"
            f"Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " Report what your tools support; another agent decides the trade."
                    " You have access to the following tools: {tool_names}."
                    " Today's date is {current_date}; treat it as 'now' for all analysis and tool-call date ranges. {instrument_context}\n"
                    "{system_message}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in TOOLS]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        result, report = take_turn(prompt, llm, TOOLS, state["messages"])

        return {
            "messages": [result],
            "news_report": report,
        }

    return news_analyst_node
