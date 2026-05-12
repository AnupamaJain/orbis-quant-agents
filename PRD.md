# Product Requirements Document (PRD): Orbis Quant Agents

**Version:** 1.0  
**Status:** Live / Production-Ready  
**Brand:** Orbis Quant AI  

---

## 1. Executive Summary
**Orbis Quant Agents** is an autonomous, multi-agent quantitative trading and research framework. Unlike traditional single-agent AI tools, Orbis utilizes a **"Firm" Architecture**, where specialized AI agents (Analysts, Researchers, Traders) collaborate and debate to eliminate bias and deliver high-conviction investment strategies. 

The framework is uniquely optimized for the **Indian Equity Market (NSE/BSE)**, featuring deep-domain awareness of regional macroeconomic factors and specialized data connectors for SEBI corporate filings and institutional activity.

---

## 2. Problem Statement
Retail and professional investors in the Indian market face three primary challenges:
1.  **Information Overload**: Managing news, social media sentiment, and government filings (SEBI) across thousands of stocks.
2.  **Cognitive Bias**: Relying on a single analytical perspective when making trading decisions.
3.  **Complexity of PSU/Small Caps**: These stocks move on specific government catalysts (tenders, order wins) that traditional fundamental tools often ignore.

---

## 3. Goals & Objectives
-   **Autonomous Research**: Automate the end-to-end intelligence gathering for any ticker.
-   **Structured Debate**: Use a Bull vs. Bear debate mechanism to pressure-test investment ideas.
-   **Indian Market Specialization**: Provide first-class support for Indian equity catalysts.
-   **Universal Accessibility**: Offer both a power-user CLI and a premium web-based dashboard.

---

## 4. Key Features

### 4.1. The "Firm" Architecture (Multi-Agent Workflow)
The framework orchestrates a sequential and iterative workflow:
1.  **Analyst Team**: Gathers data (Technical, Fundamental, News, Social).
2.  **Research Team**: A Bull and a Bear researcher debate the findings.
3.  **Research Manager**: Acts as a judge to synthesize the debate into a plan.
4.  **Trader**: Formulates an execution strategy based on the research.
5.  **Risk Management**: Three analysts (Aggressive, Neutral, Conservative) evaluate risk.
6.  **Portfolio Manager**: Issues the final BUY/HOLD/SELL decision.

### 4.2. Indian Market Optimization
-   **SEBI Filing Connector**: Automatically tracks recent corporate announcements and regulatory filings from NSE/BSE.
-   **Institutional Tracker**: Monitors Bulk and Block deals to identify FII/DII interest.
-   **Small Cap & PSU Analyst**: A specialized agent that monitors government tenders, order wins, and PLI scheme impacts.
-   **Macroeconomic Context**: Built-in awareness of RBI policy, Union Budgets, and monsoon impacts.

### 4.3. Dual-Interface System
-   **Interactive CLI**: A high-speed terminal interface for power users with rich formatting and real-time logging.
-   **Streamlit Dashboard**: A premium web interface featuring:
    -   Real-time agent progress tracking.
    -   Interactive Plotly charts (Candlestick + Indicators).
    -   Side-by-side debate visualization.

---

## 5. Technical Stack
-   **Orchestration**: LangGraph (Stateful multi-agent orchestration).
-   **LLM Clients**: OpenAI (GPT-4o/5), Anthropic (Claude 3.5), Google (Gemini 1.5/2.0), Ollama (Local).
-   **Web UI**: Streamlit.
-   **Visualization**: Plotly.
-   **Data Ingestion**: YFinance, custom Indian Data Scrapers.
-   **State Management**: FinancialSituationMemory (Local JSON-based persistence).

---

## 6. User Personas
1.  **The Quantitative Researcher**: Uses the framework to generate high-conviction research papers and strategy backtests.
2.  **The Active Retail Trader**: Uses the "Deep Think" mode for Small Caps to catch PSU momentum rallies.
3.  **The Risk Manager**: Uses the multi-agent risk debate to sanity-check large position entries.

---

## 7. Roadmap (Future Enhancements)
-   **Phase 2**: Integration with Indian brokers (Dhan/Zerodha) for automated paper trading.
-   **Phase 3**: Hindi and regional language support for final reports.
-   **Phase 4**: On-chain data integration for Hybrid Finance (CeFi + DeFi) analysis.

---

## 8. Success Metrics
-   **Reasoning Quality**: Percentage of reports that identify the core catalyst correctly.
-   **Execution Speed**: Reducing the "Time-to-Insight" for a full fundamental audit from hours to minutes.
-   **User Engagement**: Adoption of the Streamlit dashboard vs. traditional research methods.

---
**Orbis Quant AI**  
*The Future of Autonomous Financial Intelligence*
