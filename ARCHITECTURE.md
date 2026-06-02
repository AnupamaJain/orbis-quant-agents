# ORBIS QUANT AGENTS — ARCHITECTURE DOCUMENT

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DOCUMENT     : System Architecture & Design Diagrams
VERSION      : 2.0 — Institutional Release
BRAND        : Orbis Quant AI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 1. High-Level Design (HLD)

The HLD illustrates the major system boundaries, external integrations, and how the User interacts with the platform at a 30,000-foot view.

```mermaid
graph TB
    subgraph Users ["👤 User Interfaces"]
        CLI["🖥️ Interactive CLI\n(Rich Terminal)"]
        WEB["🌐 Web Dashboard\n(Streamlit)"]
        API["⚙️ Python API\n(Developer Integration)"]
    end

    subgraph Core ["🧠 Orbis Quant Core Engine"]
        ORCH["LangGraph Orchestrator\n(orbis_quant_graph.py)"]
        STATE["Global AgentState\n(TypedDict)"]
        COND["Conditional Router\n(conditional_logic.py)"]
    end

    subgraph AgentFirm ["🏛️ The Autonomous Platform"]
        L1["Layer 1: Intelligence\n(5x Analyst Agents)"]
        L2["Layer 2: Debate\n(Bull + Bear Researchers)"]
        L3["Layer 3: Risk Audit\n(3x Risk Analysts)"]
        L4["Layer 4: Synthesis\n(Portfolio Manager)"]
    end

    subgraph DataSources ["📡 Data Sources"]
        YF["yFinance\n(OHLCV + Technicals)"]
        SEBI["NSE/BSE Filings\n(SEBI Scraper)"]
        BD["Bulk/Block Deals\n(NSE Data)"]
        GT["Govt Tenders\n(CPWD/HAL/BEL)"]
        NEWS["News & Social\n(RSS + Web Search)"]
    end

    subgraph LLMLayer ["🤖 LLM Providers"]
        GPT["OpenAI GPT-4o/5"]
        GEM["Google Gemini 2.0"]
        CLD["Anthropic Claude 3.5"]
        OLL["Ollama (Local)"]
    end

    CLI & WEB & API --> ORCH
    ORCH <--> STATE
    ORCH --> COND
    COND --> L1 --> L2 --> L3 --> L4
    L1 & L2 & L3 & L4 <--> STATE

    L1 --> DataSources
    L1 & L2 & L3 & L4 --> LLMLayer

    L4 --> CLI & WEB & API
```

---

## 2. Component Architecture Diagram

This shows the internal package structure and how modules depend on each other.

```mermaid
graph LR
    subgraph entrypoints ["Entry Points"]
        main["main.py\n(CLI Entry)"]
        webui["web_ui.py\n(Streamlit Entry)"]
    end

    subgraph graph ["orbisquantagents/graph/"]
        oqg["orbis_quant_graph.py\n(Executor)"]
        setup["setup.py\n(Node/Edge Registration)"]
        cond["conditional_logic.py\n(Router)"]
        prop["propagation.py\n(State Propagation)"]
    end

    subgraph agents ["orbisquantagents/agents/"]
        analysts["analysts/\nmarket, news,\nfundamentals,\nsocial, small_cap"]
        researchers["researchers/\nbull, bear"]
        risk["risk_mgmt/\naggressive, neutral,\nconservative"]
        managers["managers/\nresearch_manager,\nportfolio_manager"]
        trader["trader/\ntrader.py"]
        utils["utils/\nagent_states.py\nagent_utils.py\nnews_data_tools.py\ncore_stock_tools.py"]
    end

    subgraph dataflows ["orbisquantagents/dataflows/"]
        interface["interface.py\n(Data Router)"]
        indian["indian_data.py\n(SEBI/Bulk/Tenders)"]
        yf["y_finance.py"]
        stockstats["stockstats_utils.py"]
        av["alpha_vantage*.py"]
    end

    subgraph llmclients ["orbisquantagents/llm_clients/"]
        factory["factory.py\n(LLMClientFactory)"]
        openai_c["openai_client.py"]
        google_c["google_client.py"]
        anthropic_c["anthropic_client.py"]
        ollama_c["base_client.py"]
    end

    main & webui --> oqg
    oqg --> setup & cond & prop
    setup --> agents
    agents --> utils & dataflows & llmclients
    dataflows --> interface --> indian & yf & stockstats & av
    llmclients --> factory --> openai_c & google_c & anthropic_c & ollama_c
```

---

## 3. Data Flow Diagram (DFD) — Full Analysis Run

This traces exactly how data moves from user input to final report.

```mermaid
flowchart TD
    A([User: Enter Ticker RELIANCE.NS]) --> B[OrbisQuantAgentsGraph.propagate]
    B --> C{Initialize AgentState\nticker, date, config}
    C --> D[Load Graph from setup.py]

    D --> E1[Market Analyst Node]
    D --> E2[Fundamentals Analyst Node]
    D --> E3[News Analyst Node]
    D --> E4[Social Analyst Node]
    D --> E5[Small Cap Analyst Node]

    E1 -->|calls| F1[yFinance: OHLCV + Indicators]
    E2 -->|calls| F2[yFinance Fundamentals\nSEBI Filings\nBulk/Block Deals]
    E3 -->|calls| F3[News RSS Feed\nWeb Search]
    E4 -->|calls| F4[Social Sentiment Tools]
    E5 -->|calls| F5[Govt Tender Scraper\nNSE/BSE Filings]

    F1 & F2 & F3 & F4 & F5 -->|raw data| G[LLM Reasoning\nper agent]
    G -->|analyst reports| H[(AgentState Updated\nwith 5 reports)]

    H --> I[Bull Researcher Node]
    H --> J[Bear Researcher Node]
    I -->|Bull Thesis| K[(AgentState)]
    J -->|Bear Thesis| K

    K --> L[Research Manager Node]
    L -->|Investment Plan| M[(AgentState)]

    M --> N[AI Trader Node]
    N -->|Technical Setup\nEntry/SL/Targets| O[(AgentState)]

    O --> P1[Aggressive Risk Analyst]
    O --> P2[Neutral Risk Analyst]
    O --> P3[Conservative Risk Analyst]
    P1 & P2 & P3 -->|Risk Reports| Q[(AgentState)]

    Q --> R[Portfolio Manager Node]
    R -->|Final Signal\nBUY/SELL/HOLD + Confidence%| S[Final Report Output]

    S --> T1[CLI: Rich Table Display]
    S --> T2[Web: Streamlit Dashboard]
    S --> T3[File: reports/RELIANCE.NS_report.md]
```

---

## 4. Agent Interaction Sequence Diagram

This shows the precise temporal ordering of agent calls.

```mermaid
sequenceDiagram
    actor User
    participant CLI as CLI / Web UI
    participant Graph as LangGraph Orchestrator
    participant State as AgentState
    participant Analysts as Analyst Team (x5)
    participant Data as Data Connectors
    participant Bull as Bull Researcher
    participant Bear as Bear Researcher
    participant RM as Research Manager
    participant Trader as AI Trader
    participant Risk as Risk Audit Team (x3)
    participant PM as Portfolio Manager

    User->>CLI: Enter ticker "RELIANCE.NS"
    CLI->>Graph: propagate("RELIANCE.NS", "2026-05-14")
    Graph->>State: Initialize AgentState{}

    loop Parallel Analyst Execution
        Graph->>Analysts: Invoke all 5 analyst nodes
        Analysts->>Data: Tool calls (yFinance, SEBI, Tenders)
        Data-->>Analysts: Raw market data returned
        Analysts->>Analysts: LLM reasoning + synthesis
        Analysts-->>State: Store analyst_report fields
    end

    Graph->>Bull: Invoke with all analyst reports
    Bull->>Bull: Construct bullish investment case
    Bull-->>State: Store bull_thesis

    Graph->>Bear: Invoke with analyst reports + bull_thesis
    Bear->>Bear: Identify weaknesses in Bull thesis
    Bear-->>State: Store bear_thesis

    Graph->>RM: Invoke with both theses
    RM->>RM: Score debate, weight evidence
    RM-->>State: Store investment_plan + direction

    Graph->>Trader: Invoke with investment_plan
    Trader->>Data: Get current technicals for entry calc
    Trader->>Trader: Compute Entry, SL, 3x Targets
    Trader-->>State: Store trader_proposal

    loop Parallel Risk Audit
        Graph->>Risk: Invoke Aggressive + Neutral + Conservative
        Risk->>Risk: Evaluate trader_proposal against risk profile
        Risk-->>State: Store risk_report
    end

    Graph->>PM: Invoke with ALL reports in AgentState
    PM->>PM: Confidence-weighted voting
    PM-->>State: Store final_decision + final_confidence
    PM-->>CLI: Return FinalDecision object

    CLI-->>User: Display BUY/SELL/HOLD with confidence %
```

---

## 5. State Machine Diagram (LangGraph Node States)

This shows the valid state transitions within the LangGraph execution.

```mermaid
stateDiagram-v2
    [*] --> GraphInitialized

    GraphInitialized --> AnalystExecution : propagate() called
    
    state AnalystExecution {
        [*] --> MarketAnalyst
        [*] --> FundamentalsAnalyst
        [*] --> NewsAnalyst
        [*] --> SocialAnalyst
        [*] --> SmallCapAnalyst
        MarketAnalyst --> AnalystsComplete
        FundamentalsAnalyst --> AnalystsComplete
        NewsAnalyst --> AnalystsComplete
        SocialAnalyst --> AnalystsComplete
        SmallCapAnalyst --> AnalystsComplete
    }

    AnalystExecution --> ResearchDebate

    state ResearchDebate {
        [*] --> BullResearcher
        BullResearcher --> BearResearcher
        BearResearcher --> DebateComplete
    }

    ResearchDebate --> ResearchManager
    ResearchManager --> TraderNode

    TraderNode --> RiskAudit

    state RiskAudit {
        [*] --> AggressiveAudit
        [*] --> NeutralAudit
        [*] --> ConservativeAudit
        AggressiveAudit --> AuditComplete
        NeutralAudit --> AuditComplete
        ConservativeAudit --> AuditComplete
    }

    RiskAudit --> PortfolioManager
    PortfolioManager --> FinalSignal
    FinalSignal --> [*]

    state ConditionalRouting {
        SmallCapEnabled : Small Cap Enabled?
        SmallCapEnabled --> SmallCapAnalyst : YES
        SmallCapEnabled --> AnalystsComplete : NO (skip)
    }
```

---

## 6. Indian Data Connector — Architecture

This shows the specialized data pipeline for the Indian market.

```mermaid
flowchart LR
    subgraph Trigger ["Agent Triggers"]
        FA[Fundamentals\nAnalyst]
        SCA[Small Cap\nAnalyst]
    end

    subgraph Interface ["dataflows/interface.py\n(Central Router)"]
        Router{Tool\nDispatcher}
    end

    subgraph IndianData ["dataflows/indian_data.py"]
        SEBI["get_sebi_filings()\nScrapes NSE announcements\nExtracts PDF metadata"]
        BULK["get_bulk_block_deals()\nParses NSE bulk deal CSV\nFilters by ticker symbol"]
        TENDER["get_government_tenders()\nScrapes CPWD/HAL/BEL\nKeyword: company name + 'order'"]
    end

    subgraph Output ["Structured Output"]
        OUT1["📄 Last 5 SEBI Filings\nDate, Category, Summary"]
        OUT2["📊 Bulk/Block Deals\nBuyer, Qty, Price, % Equity"]
        OUT3["🏗️ Tender Wins\nDate, Estimated Value, Source"]
    end

    FA & SCA --> Router
    Router -->|sebi_tool| SEBI
    Router -->|bulk_deal_tool| BULK
    Router -->|tender_tool| TENDER
    SEBI --> OUT1
    BULK --> OUT2
    TENDER --> OUT3
    OUT1 & OUT2 & OUT3 --> FA & SCA
```

---

## 7. Deployment Architecture Diagram

This shows how Orbis is deployed in a containerized production environment.

```mermaid
graph TB
    subgraph Developer ["👩‍💻 Developer / User Machine"]
        ENV[".env file\n(API Keys — NEVER committed)"]
        DC["docker-compose.yml"]
    end

    subgraph Docker ["🐳 Docker Container"]
        APP["orbisquantagents\nPython 3.11 Runtime"]
        UV["uv package manager\n(Fast dependency resolution)"]
        VOL["Volume Mount: /app"]
    end

    subgraph External ["☁️ External APIs"]
        OPENAI["OpenAI API"]
        GOOGLE["Google Gemini API"]
        ANTHROPIC["Anthropic API"]
        YF_API["Yahoo Finance\n(yfinance)"]
        NSE_WEB["NSE/BSE Websites\n(Scrapers)"]
    end

    ENV -->|injected at runtime| Docker
    DC -->|builds & runs| Docker
    APP --> UV
    Docker <-->|HTTPS| OPENAI & GOOGLE & ANTHROPIC
    Docker <-->|HTTPS| YF_API & NSE_WEB
```

---

## 8. LLM Client Factory — Architecture

This shows how agents are assigned LLM providers dynamically.

```mermaid
graph TD
    Config["DEFAULT_CONFIG\nllm_provider: openai\nbackup_provider: google"]

    Factory["LLMClientFactory\n(llm_clients/factory.py)"]

    subgraph Clients ["Provider Clients"]
        OAI["OpenAIClient\nGPT-4o / GPT-4o-mini"]
        GGL["GoogleClient\nGemini 2.0 Flash / Pro"]
        ANT["AnthropicClient\nClaude 3.5 Sonnet"]
        OLL["BaseClient (Ollama)\nLocal LLMs"]
    end

    subgraph Agents ["Agents using LLMs"]
        direction TB
        A1["Market Analyst\n→ Gemini Flash (speed)"]
        A2["Research Manager\n→ GPT-4o (reasoning)"]
        A3["Bear Researcher\n→ Claude 3.5 (skepticism)"]
        A4["Portfolio Manager\n→ GPT-4o (synthesis)"]
    end

    Config --> Factory
    Factory --> OAI & GGL & ANT & OLL
    OAI --> A2 & A4
    GGL --> A1
    ANT --> A3
```

---

## 9. Bull vs. Bear Debate Flow

This zooms into the adversarial reasoning mechanism.

```mermaid
flowchart TD
    A[(AgentState with\n5 Analyst Reports)] --> B

    subgraph BullProcess ["⬆️ Bull Researcher"]
        B[Read all analyst reports]
        B --> C[Identify top 5\npositive catalysts]
        C --> D[Weight upside evidence\nMinimize risk signals]
        D --> E[Set Price Target\nEntry Strategy]
        E --> F[Generate Bull Thesis Doc]
    end

    F --> G

    subgraph BearProcess ["⬇️ Bear Researcher"]
        G[Read analyst reports\n+ Bull Thesis]
        G --> H[Identify factual errors\nin Bull Thesis]
        H --> I[Find overlooked risks\nMacro / Technical / Fundamental]
        I --> J[Set Downside Target\nExit Scenarios]
        J --> K[Generate Bear Thesis Doc]
    end

    K --> L

    subgraph JudgeProcess ["⚖️ Research Manager"]
        L[Score Bull Thesis\nCredibility 0-10\nEvidence 0-10\nConsistency 0-10]
        L --> M[Score Bear Thesis\nSame rubric]
        M --> N{Weighted Verdict}
        N -->|Bull Score Higher| O[Long / Buy Bias]
        N -->|Bear Score Higher| P[Short / Avoid Bias]
        N -->|Near Equal| Q[Neutral / Hold Bias]
        O & P & Q --> R[Generate Investment Plan\nwith Confidence %]
    end
```

---

## 10. Risk Audit Flow

```mermaid
flowchart LR
    TP["Trader Proposal\nEntry: ₹2,850\nSL: ₹2,780\nTarget 1: ₹3,000\nTarget 2: ₹3,150\nTarget 3: ₹3,300\nR/R: 1:2.5"]

    subgraph Audit ["Parallel Risk Audit (3 Agents)"]
        AGG["Aggressive Analyst\n• Focus: Max upside capture\n• Validates: Target 3 achievable?\n• Output: Approve with\n  larger position size"]
        NEU["Neutral Analyst\n• Focus: Objective R/R\n• Validates: SL placement\n• Output: Approve at\n  standard position size"]
        CON["Conservative Analyst\n• Focus: Capital preservation\n• Validates: Black swan risk\n• Output: Reduce position\n  by 30%, tighten SL"]
    end

    TP --> AGG & NEU & CON

    AGG & NEU & CON --> PM

    PM["Portfolio Manager\nWeights: Aggressive=25%\nNeutral=50%\nConservative=25%\n\n→ Final: APPROVED\n   Position: Standard (-15%)\n   Confidence: 74%"]
```

---

*All diagrams are rendered using Mermaid.js and display natively on GitHub.*

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    ORBIS QUANT AI   |   github.com/AnupamaJain/orbis-quant-agents
    YouTube: @growthblueprint-ai   |   Instagram: @growthblueprintai
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```
