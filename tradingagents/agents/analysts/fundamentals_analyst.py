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

        system_message = (
            "You are a researcher tasked with analyzing fundamental information about an instrument (stock, mutual fund, or ETF)."
            " Please write a comprehensive fundamental report to inform traders. Make sure to include as much detail as possible."
            " Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            " Make sure to append a Markdown table at the end of the report to organize key metrics."
            " Use the available tools based on the instrument type:"
            " - For stocks: Use `get_fundamentals` for company overview (P/E, ROCE, EBITDA, Sales, Net Profit), `get_balance_sheet`, `get_cashflow`, `get_income_statement`, and `get_insider_transactions`."
            " - For Indian Mutual Funds: Use `get_mutual_fund_info` to analyze AMFI NAV, trailing returns (1M, 6M, 1Y, 3Y, 5Y CAGR), scheme category, and AMC fund house."
            " - For ETFs: Use `get_etf_info` to analyze the underlying benchmark index, market pricing, and trading volume."
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
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
