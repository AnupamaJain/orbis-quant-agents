import re
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
        "\n\n**CRITICAL OUTPUT RULES (NON-NEGOTIABLE):**\n"
        "1. **NO CODE EVER**: Do NOT write Python, JavaScript, JSON, or any programming code. Do NOT use ```python```, "
        "```json```, `import`, `print()`, `json.dumps`, or any code-like syntax. This is absolutely forbidden.\n"
        "2. **WRITE PROSE ONLY**: Your entire response must be in clean Markdown with natural language paragraphs, "
        "bullet lists, and/or markdown tables. No code blocks of any kind.\n"
        "3. **NO PLACEHOLDERS**: Do not write '...' or placeholder text. Write actual analysis based on the tool data you received.\n"
        "4. **GROUND IN TOOL RESULTS**: Every claim must reference data actually returned by the tools. "
        "Do not invent numbers, prices, PE ratios, or any metric not explicitly present in the tool output."
    )
    
    return context

def get_grounding_instruction() -> str:
    """Return a strict anti-hallucination instruction for debate and verdict agents.
    
    These agents receive analyst reports as context and must not fabricate any data
    not present in those reports. This instruction is injected into their prompts.
    """
    return (
        "\n\n**CRITICAL ANTI-HALLUCINATION RULES:**\n"
        "- **Only cite data that appears in the analyst reports above.** "
        "Do NOT invent, assume, or extrapolate any financial figures, prices, PE ratios, revenues, "
        "EPS numbers, promoter holdings, or any other metric.\n"
        "- If a specific data point is not in the reports, say 'data not available' — do not make it up.\n"
        "- Base your BUY/SELL/HOLD verdict solely on the evidence provided by the analysts. "
        "Do not bring in external knowledge about the company that contradicts the reports.\n"
        "- **NO CODE**: Do not output any Python code, JSON snippets, or programming syntax. "
        "Write in plain Markdown prose only."
    )


def sanitize_report(text: str) -> str:
    """Strip accidental code blocks from analyst LLM output.

    The LLM occasionally produces Python/JSON code blocks despite prompt
    instructions. This post-processor catches and removes them so the
    UI always renders clean Markdown prose.
    """
    if not text:
        return text

    # Remove fenced code blocks (```python ... ``` or ```json ... ``` etc.)
    cleaned = re.sub(
        r"```[a-zA-Z]*\n.*?```",
        "[Note: Code output was suppressed — refer to the analysis text above]",
        text,
        flags=re.DOTALL,
    )

    # Remove bare ``` blocks too (no language specifier)
    cleaned = re.sub(
        r"```\n.*?```",
        "[Note: Code output was suppressed]",
        cleaned,
        flags=re.DOTALL,
    )

    # Remove stray import / from ... import lines
    cleaned = re.sub(r"^import\s+\w+.*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^from\s+\w+\s+import.*$", "", cleaned, flags=re.MULTILINE)

    # Remove print() statements
    cleaned = re.sub(r"^print\(.*\)$", "", cleaned, flags=re.MULTILINE)

    # Collapse excess blank lines left after removal
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    return cleaned


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
