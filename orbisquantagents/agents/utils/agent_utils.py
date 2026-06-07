from langchain_core.messages import HumanMessage, RemoveMessage

# Import tools from separate utility files
from orbisquantagents.agents.utils.core_stock_tools import (
    get_stock_data
)
from orbisquantagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from orbisquantagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_sebi_filings,
    get_bulk_block_deals,
)
from orbisquantagents.agents.utils.news_data_tools import (
    get_news,
    get_insider_transactions,
    get_global_news,
    get_government_tenders,
)


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Only applied to user-facing agents (analysts, portfolio manager).
    Internal debate agents stay in English for reasoning quality.
    """
    from orbisquantagents.dataflows.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


def build_instrument_context(ticker: str) -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers and understand regional context."""
    context = (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`, `.NS`, `.BO`)."
    )
    
    if ticker.upper().endswith(".NS") or ticker.upper().endswith(".BO"):
        context += (
            "\nContext: This is an Indian company. When performing research, focus on Indian macroeconomic drivers "
            "(e.g., RBI interest rate decisions, Indian Union Budget, monsoon impact on consumption) and "
            "reference insights from Indian financial news outlets like Moneycontrol, The Economic Times, or Mint."
        )
    
    context += (
        "\nFormatting Instruction: Your output report must be a direct, readable analysis in clean Markdown (using "
        "standard paragraphs, bullet points, or markdown tables). **NEVER write, simulate, or output Python code, "
        "scripts, print statements, or mock JSON code blocks (e.g. do not output code blocks starting with `python ...` "
        "or `import json`).** Write out your analysis, findings, and recommendations directly in markdown text."
    )
    
    return context

def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages


        
