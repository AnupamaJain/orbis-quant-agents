# Low-Level Design (LLD): Agent Internals

This document details the internal logic and operational flow for each agent class within the **Orbis Quant Agents** framework.

---

## 1. Analyst Agents (Intelligence Layer)
*Types: Market, News, Fundamentals, Social, Small-Cap*

### Logic Flow
Analyst agents are "tool-use" specialists. They follow a loop of observing data, reasoning about its relevance, and synthesizing it into a structured markdown report.

```mermaid
graph TD
    Start[Graph Node Start] --> SystemPrompt[Load Agent System Message]
    SystemPrompt --> InputState[Receive AgentState: ticker, date]
    InputState --> ToolSelection{Reasoning: Which tools needed?}
    
    ToolSelection -->|Market| TA[Technical Indicator Tools]
    ToolSelection -->|News| NT[News & Sentiment Tools]
    ToolSelection -->|Indian| IT[SEBI & Tender Tools]
    
    TA & NT & IT --> DataGathering[Execution: Concurrent Tool Calls]
    DataGathering --> Analysis[LLM Reasoning: Pattern Recognition]
    Analysis --> ReportGen[Generate Structured MD Report]
    ReportGen --> UpdateState[Update AgentState: analyst_report]
```

---

## 2. Researcher Agents (Debate Layer)
*Types: Bull Researcher, Bear Researcher*

### Logic Flow
Researchers are designed for "adversarial reasoning." They do not just summarize; they actively defend a specific market bias (Long or Short) by selectively weighting evidence.

```mermaid
graph TD
    Input[Receive Analyst Reports] --> Bias[Apply Bias: Bullish or Bearish]
    Bias --> Evidence[Search Reports for Supporting Evidence]
    Evidence --> CounterArgument[Analyze Weaknesses in Opposite View]
    CounterArgument --> Debate[Generate Argument for Debate History]
    Debate --> Reflection{Is Debate Finished?}
    Reflection -->|No| Debate
    Reflection -->|Yes| FinalThesis[Finalize Thesis for Manager]
```

---

## 3. Trader Agent (Strategy Layer)
*Type: Trader*

### Logic Flow
The Trader acts as the "Architect" of the trade. It takes abstract research and converts it into a concrete technical setup.

```mermaid
graph TD
    Thesis[Receive Research Thesis] --> Setup[Identify Technical Entry/Exit]
    Setup --> IndicatorCheck[Call Technical Tools for Confirmation]
    IndicatorCheck --> Confidence[Calculate Conviction Level]
    Confidence --> Plan[Draft Trader Investment Plan]
    Plan --> RiskPass[Handoff to Risk Management]
```

---

## 4. Risk Management Team (Audit Layer)
*Types: Aggressive, Conservative, Neutral*

### Logic Flow
Risk agents perform a "scenario-based audit." They look for what could go wrong rather than what could go right.

```mermaid
flowchart LR
    Plan[Investment Plan] --> Agg[Aggressive Analyst: Focus on Upside Capture]
    Plan --> Con[Conservative Analyst: Focus on Capital Preservation]
    Plan --> Neu[Neutral Analyst: Focus on Risk/Reward Ratio]
    
    Agg & Con & Neu --> Debate[Risk Debate Loop]
    Debate --> FinalAudit[Final Risk Score & Mitigation Tips]
```

---

## 5. Portfolio Manager (Decision Layer)
*Type: Portfolio Manager*

### Logic Flow
The PM is the final synthesizer. It uses a "Confidence-Weighted Voting" logic to produce the final signal.

```mermaid
graph TD
    Inputs[All Reports + Debate + Risk Audit] --> Weighting[Weight Analysts vs Researchers]
    Weighting --> SignalLogic{Final Signal Decision}
    SignalLogic -->|High Conviction| Buy[Strong BUY]
    SignalLogic -->|Medium Conviction| Hold[HOLD / Neutral]
    SignalLogic -->|Negative| Sell[SELL / Avoid]
    
    Buy & Hold & Sell --> FinalReport[Generate Executive Summary]
```

---
**Orbis Quant AI**  
*Internal Agent Design Documentation*
