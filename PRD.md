# PRODUCT REQUIREMENTS DOCUMENT: ORBIS QUANT AGENTS

**Project:** Autonomous Multi-Agent Financial Intelligence Firm (Indian Equity Specialized)  
**Version:** 1.1 | **Date:** May 2026  
**Status:** Production-Ready / Public Release  
**Brand:** Orbis Quant AI

---

## 1. Executive Summary
### 1.1 Product Vision
**Orbis Quant Agents** is designed to democratize high-conviction quantitative research by providing an "Institutional-Grade Research Firm in a Box." The product enables retail and professional investors in the Indian market to move from a ticker symbol to a 10-page, adversarial, and risk-audited investment thesis in under 5 minutes.

### 1.2 Key Differentiators
- **Adversarial Reasoning**: Unlike single-agent LLM bots, Orbis uses a "Bull vs. Bear" debate mechanism to eliminate cognitive bias and hallucination.
- **Indian Market Specialization**: First-of-its-kind specialized connectors for SEBI corporate filings, NSE/BSE Bulk/Block deals, and PSU-specific government tender tracking.
- **Stateful Intelligence**: Built on LangGraph, the system maintains a complex state that allows for reflection, self-correction, and long-term research continuity.

---

## 2. Problem Statement
### 2.1 The Retail Gap
Retail investors in India lack access to real-time institutional-grade intelligence. Corporate filings (SEBI) and high-value deal data (Bulk/Block) are often buried in PDFs or expensive terminal subscriptions.
### 2.2 Cognitive Bias
Most traders suffer from "Confirmation Bias." Orbis solves this by making a **Bear Analyst** a mandatory part of every decision flow, ensuring that "pumps" are met with technical skepticism.

---

## 3. Agentic AI Design (The "Firm" Architecture) 🤖
The framework follows a hierarchical and adversarial "Firm" model.

### 3.1 The Orchestration Layer (LangGraph)
The system operates as a stateful Directed Acyclic Graph (DAG). 
- **Nodes**: Specialized Agents.
- **Edges**: Conditional logic based on analyst confidence scores and market volatility.

### 3.2 The Intelligence Tools (The Hands)
- **Primary Data**: yFinance API for real-time OHLCV and technicals.
- **Specialized Scrapers**: Custom Python dataflows for NSE/BSE tender announcements and SEBI filing extraction.
- **Social Connectors**: Sentiment analysis tools for X (Twitter) and Telegram stock communities.

### 3.3 The Memory System
- **Ephemeral State**: Shared `AgentState` object passing reports between nodes.
- **Persistence Layer**: JSON-based `FinancialSituationMemory` for storing past debates and ticker-specific insights to avoid redundant API costs.

### 3.4 Guardrails & Logic
- **Budget Control**: Configurable token limits per analysis run.
- **Ticker Validation**: Automated suffix injection (`.NS` / `.BO`) to ensure data accuracy for the Indian market.

---

## 4. Feature Breakdown & Pillars

### Pillar 1: Data Ingestion & Localization
- **SEBI Filing Tracker**: Parses regulatory announcements for key management changes or legal updates.
- **PSU/Small-Cap Analyst**: Specialized toolset to monitor government order wins and PLI scheme catalysts.

### Pillar 2: The Adversarial Strategy Lab
- **Bullish Researcher**: High-conviction growth analysis.
- **Bearish Researcher**: "Devil's Advocate" logic focusing on overvaluation and macro headwinds.
- **Research Manager**: The "Judge" node that synthesizes the debate into a single, high-conviction thesis.

### Pillar 3: Technical Execution & Risk Audit
- **The AI Trader**: Converts the abstract thesis into a technical setup (Entry, Target, Stop-Loss).
- **Risk Audit Swarm**: Three agents (Aggressive, Neutral, Conservative) audit the trader's plan against current market volatility.

### Pillar 4: Portfolio Management & UI
- **Executive Summary Gen**: Produces a final BUY/SELL/HOLD report with a confidence percentage.
- **Premium Dashboard**: Streamlit interface with live Plotly charts and "The Debate Arena" visualization.

---

## 5. Technical Stack 🛠️
- **Framework**: LangGraph, LangChain.
- **UI/UX**: Streamlit (Web), Rich (CLI).
- **Data Visualization**: Plotly (Interactive Charts).
- **LLM Support**: GPT-4o (Primary), Gemini 2.0 (Analysis), Claude 3.5 (Reasoning).
- **Environment**: UV-managed Python environment, Dockerized deployment.

---

## 6. Appendix: The Agent Roster
| Agent Name | Role | Core Responsibility |
| :--- | :--- | :--- |
| **Market Analyst** | Technicals | Patterns, RSI, MACD, Volume Profile. |
| **Small-Cap Analyst** | Catalysts | PSU Tenders, Order Wins, PLI schemes. |
| **Bull Researcher** | Optimist | Defending the Long thesis. |
| **Bear Researcher** | Skeptic | Identifying the Short thesis / Risks. |
| **Risk Auditor** | Protection | Stress-testing the position size and targets. |
| **Portfolio Manager** | Decision | Final BUY/SELL signal synthesis. |

---
**Orbis Quant AI**  
*The Future of Autonomous Financial Intelligence*
