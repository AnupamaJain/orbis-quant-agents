# Project Context: Orbis Quant Agents

## 🌌 Project Vision
**Orbis Quant Agents** is an autonomous, multi-agent financial intelligence firm. It transforms the solitary AI analysis experience into a collaborative, "firm-like" workflow where specialized agents (Analysts, Researchers, Traders) interact, debate, and refine investment strategies.

## 🏛️ Core Architecture: The "Firm" Model
Every analysis follows a structured path:
1.  **Analyst Team**: (Market, Social, News, Fundamentals, Small-Cap) - These agents are data gatherers.
2.  **Researcher Team**: (Bull vs. Bear) - These agents debate the findings to surface risks and opportunities.
3.  **Research Manager**: Synthesizes the debate into a coherent investment thesis.
4.  **Trader**: Translates the thesis into an actionable execution plan.
5.  **Risk Management**: (Aggressive, Conservative, Neutral) - A secondary debate to stress-test the plan.
6.  **Portfolio Manager**: The final decision-maker (BUY/SELL/HOLD).

## 🇮🇳 Market Focus: Indian Equities (NSE/BSE)
-   **Tickers**: Preserve suffixes (e.g., `.NS` for NSE, `.BO` for BSE).
-   **Specialized Connectors**: SEBI filings, Bulk/Block deals, and PSU/Small-Cap tender wins.
-   **Macro Context**: Awareness of RBI, Union Budget, and monsoon-driven consumption.

## 🛠️ Technical Stack
-   **Orchestration**: LangGraph (Stateful Agent Graphs).
-   **LLM Interface**: LangChain.
-   **UI**: Dual-mode (Interactive CLI + Streamlit Dashboard).
-   **Data**: YFinance (Primary), Custom Indian Scrapers (Secondary).

## 📝 Coding Principles & Constraints
1.  **Modularity**: Agents are independent nodes in the graph (`orbisquantagents/agents/`).
2.  **State Management**: Use `AgentState` for persistence across the graph.
3.  **No Secrets**: Never hardcode API keys. Use `.env`.
4.  **Relative Paths**: All file operations must be relative to the project root or configurable via `DEFAULT_CONFIG`.
5.  **Branding**: Always refer to the project as **Orbis Quant Agents**.

## 📁 Key Directories
-   `orbisquantagents/agents/`: Specialized agent logic.
-   `orbisquantagents/graph/`: Orchestration and conditional routing logic.
-   `orbisquantagents/dataflows/`: Data connectors and vendor logic.
-   `cli/`: Terminal interface components.
-   `web_ui.py`: The Streamlit dashboard.

---
*This context should be loaded by any AI assistant working on this repository to ensure alignment with the Orbis Quant methodology.*
