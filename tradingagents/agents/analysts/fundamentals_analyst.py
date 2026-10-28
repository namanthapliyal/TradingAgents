from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.analysts.turn import take_turn
from tradingagents.agents.context import get_instrument_context_from_state, get_language_instruction
from tradingagents.agents.tools import (
    get_balance_sheet,
    get_cashflow,
    get_etf_info,
    get_fundamentals,
    get_income_statement,
    get_insider_transactions,
    get_mutual_fund_info,
)

# The tools this analyst is offered; its tool node is built from the same tuple.
TOOLS = (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_insider_transactions,
    get_mutual_fund_info,
    get_etf_info,
)


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)
        asset_type = state.get("asset_type", "stock")
        ticker = state.get("company_of_interest", "")

        # Select primary tool ordering based on instrument type
        if asset_type in ("mutual_fund", "mf") or (ticker.isdigit() and len(ticker) >= 5):
            ordered_tools = (
                get_mutual_fund_info,
                get_fundamentals,
                get_balance_sheet,
                get_cashflow,
                get_income_statement,
                get_insider_transactions,
                get_etf_info,
            )
        elif asset_type == "etf":
            ordered_tools = (
                get_etf_info,
                get_fundamentals,
                get_balance_sheet,
                get_cashflow,
                get_income_statement,
                get_insider_transactions,
                get_mutual_fund_info,
            )
        else:
            ordered_tools = TOOLS

        system_message = (
            "You are a professional fundamental research analyst tasked with analyzing the financial health, "
            "valuation, and earnings quality of an instrument (stock, mutual fund, or ETF).\n\n"
            "MANDATORY EXECUTION RULES:\n"
            "1. GROUNDING IN TOOL DATA: You MUST call your data tools first (e.g. `get_fundamentals`). "
            "Never invent, assume, or hallucinate financial figures, valuation multiples, or business activities. "
            "Every metric in your report must be directly cited from the tool output.\n"
            "2. INDIAN FINANCIAL SCALING & CURRENCY:\n"
            "   - All absolute figures for Indian equities are denominated in **Indian Rupees (INR) Crores (₹ Cr)**.\n"
            "   - 1 Crore (Cr) = 10,000,000 INR (10 Million INR = ₹1 Cr). 1 Lakh Crore = 100,000 Crore (₹1 Trillion).\n"
            "   - Report sales, net profit, EBITDA, and market cap in **₹ Crore (Cr)** or **₹ Lakh Crore**. "
            "DO NOT confuse Crores with millions or single rupees. For example, ₹191,059 Cr is ₹1.91 Lakh Crore (NOT ₹191,059 or 191 Million).\n"
            "   - Quote the exact figures returned by the tools: Sales TTM (Cr), Net Profit TTM (Cr), "
            "Operating Profit / EBITDA (Cr), Operating Margin (OPM %), Market Cap (Cr), ROCE (%), ROE (%), Stock P/E, Book Value.\n"
            "3. CORE BUSINESS & SECTOR INTEGRITY: You MUST adhere strictly to the company's verified sector and industry "
            "provided in the instrument context. NEVER claim or speculate that the company operates in an unrelated sector "
            "(e.g. do not misidentify a power utility as heavy machinery, or a bank as an IT company).\n"
            "4. Make sure to append a Markdown table at the end of the report summarizing the verified key metrics."
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
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in ordered_tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        result, report = take_turn(prompt, llm, ordered_tools, state["messages"])

        return {
            "messages": [result],
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
