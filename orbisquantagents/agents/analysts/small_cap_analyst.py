from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from orbisquantagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_news,
    get_government_tenders,
    get_language_instruction,
)

def create_small_cap_analyst(llm):
    """
    A specialized analyst for Indian Small Caps and PSU stocks.
    Focuses on government order wins, tenders, and sector-specific catalysts.
    """
    def small_cap_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_news,
            get_government_tenders,
        ]

        system_message = (
            "You are a specialized 'Small Cap & PSU' Analyst for the Indian market. Your mission is to identify specific catalysts that drive low-float or government-owned stocks. "
            "Focus specifically on: \n"
            "1. **Government Tender Wins**: Use `get_government_tenders` to find recent contract awards or project allocations.\n"
            "2. **Order Book Strength**: Analyze how new orders impact the company's future revenue.\n"
            "3. **Sectoral Tailwinds**: Look for news on PLI schemes, infrastructure spending, or policy changes affecting the company's sector.\n"
            "Provide a detailed report on these high-impact catalysts. If the stock is a PSU (Public Sector Undertaking), explicitly mention the government's stance or divestment news."
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
            report = result.content

        return {
            "messages": [result],
            "small_cap_report": report,
        }

    return small_cap_analyst_node
