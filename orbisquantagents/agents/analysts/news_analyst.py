import re
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from orbisquantagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_global_news,
    get_language_instruction,
    get_news,
)
from orbisquantagents.dataflows.config import get_config


def _sanitize_report(text: str) -> str:
    """
    Remove any Python/JSON code blocks from the report.
    
    If the LLM accidentally outputs a code block (e.g. ```python ... ```),
    this strips it out and replaces it with a note so the report stays clean.
    Code blocks are a hallucination artifact — we want pure prose.
    """
    if not text:
        return text

    # Remove fenced code blocks (```python ... ``` or ``` ... ```)
    cleaned = re.sub(
        r"```[a-zA-Z]*\n.*?```",
        "[Code block removed — see analyst report above for actual data]",
        text,
        flags=re.DOTALL,
    )

    # Remove any inline `import` statements that sneak through
    cleaned = re.sub(r"^import\s+\w+.*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^from\s+\w+\s+import.*$", "", cleaned, flags=re.MULTILINE)

    # Remove print() statements
    cleaned = re.sub(r"^print\(.*\)$", "", cleaned, flags=re.MULTILINE)

    # Clean up excess blank lines left after removal
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    return cleaned


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_news,
            get_global_news,
        ]

        system_message = (
            "You are a news researcher tasked with analyzing recent news and trends over the past week. "
            "Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. "
            "Use the available tools: get_news(ticker, start_date, end_date) for company-specific or targeted news searches, "
            "and get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news. "
            "Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
            "\n\n"
            "ABSOLUTE RULE — YOUR RESPONSE MUST BE PLAIN MARKDOWN TEXT ONLY:\n"
            "- DO NOT write any Python code, JSON code, or programming code of any kind.\n"
            "- DO NOT use 'import', 'print()', 'json.dumps()', or any code-like syntax.\n"
            "- DO NOT output code blocks (no ``` blocks).\n"
            "- Write your report entirely in readable English prose with markdown formatting (headers, bullets, tables).\n"
            "- Summarize what the news tools actually returned. Do not invent or hallucinate news articles.\n"
            "- If a tool returns no news, state 'No news found for this query' — do not make up articles."
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
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            # Sanitize the final report to remove any accidentally generated code
            report = _sanitize_report(result.content)

        return {
            "messages": [result],
            "news_report": report,
        }

    return news_analyst_node
