# Orbis Quant Agents/graph/orbis_quant_graph.py

import os
from pathlib import Path
import json
from datetime import date
from typing import Dict, Any, Tuple, List, Optional

from langgraph.prebuilt import ToolNode

from orbisquantagents.llm_clients import create_llm_client

from orbisquantagents.agents import *
from orbisquantagents.default_config import DEFAULT_CONFIG
from orbisquantagents.agents.utils.memory import FinancialSituationMemory
from orbisquantagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)
from orbisquantagents.compliance import (
    generate_session_id,
    get_execution_timestamp,
    data_sources_var,
    append_audit_log,
)
from orbisquantagents.dataflows.config import set_config

# Import the new abstract tool methods from agent_utils
from orbisquantagents.agents.utils.agent_utils import (
    get_stock_data,
    get_indicators,
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_news,
    get_insider_transactions,
    get_global_news,
    get_government_tenders,
    get_sebi_filings,
    get_bulk_block_deals
)

from .conditional_logic import ConditionalLogic
from .setup import GraphSetup
from .propagation import Propagator
from .reflection import Reflector
from .signal_processing import SignalProcessor


class OrbisQuantAgentsGraph:
    """Main class that orchestrates the trading agents framework."""

    def __init__(
        self,
        selected_analysts=["market", "social", "news", "fundamentals"],
        debug=False,
        config: Dict[str, Any] = None,
        callbacks: Optional[List] = None,
    ):
        """Initialize the trading agents graph and components.

        Args:
            selected_analysts: List of analyst types to include
            debug: Whether to run in debug mode
            config: Configuration dictionary. If None, uses default config
            callbacks: Optional list of callback handlers (e.g., for tracking LLM/tool stats)
        """
        self.debug = debug
        self.config = config or DEFAULT_CONFIG
        self.callbacks = callbacks or []
        print(f"[DEBUG] OrbisQuantAgentsGraph initialized with config: {self.config}", flush=True)

        # Update the interface's config
        set_config(self.config)

        # Create necessary directories
        os.makedirs(
            os.path.join(self.config["project_dir"], "dataflows/data_cache"),
            exist_ok=True,
        )

        # Initialize LLMs with provider-specific thinking configuration
        llm_kwargs = self._get_provider_kwargs()

        # Add callbacks to kwargs if provided (passed to LLM constructor)
        if self.callbacks:
            llm_kwargs["callbacks"] = self.callbacks

        deep_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["deep_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )
        quick_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["quick_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )

        self.deep_thinking_llm = deep_client.get_llm()
        self.quick_thinking_llm = quick_client.get_llm()
        
        # Initialize memories
        self.bull_memory = FinancialSituationMemory("bull_memory", self.config)
        self.bear_memory = FinancialSituationMemory("bear_memory", self.config)
        self.trader_memory = FinancialSituationMemory("trader_memory", self.config)
        self.invest_judge_memory = FinancialSituationMemory("invest_judge_memory", self.config)
        self.portfolio_manager_memory = FinancialSituationMemory("portfolio_manager_memory", self.config)

        # Create tool nodes
        self.tool_nodes = self._create_tool_nodes()

        # Initialize components
        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config["max_debate_rounds"],
            max_risk_discuss_rounds=self.config["max_risk_discuss_rounds"],
        )
        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.tool_nodes,
            self.bull_memory,
            self.bear_memory,
            self.trader_memory,
            self.invest_judge_memory,
            self.portfolio_manager_memory,
            self.conditional_logic,
        )

        self.propagator = Propagator()
        self.reflector = Reflector(self.quick_thinking_llm)
        self.signal_processor = SignalProcessor(self.quick_thinking_llm)

        # State tracking
        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}  # date to full state dict

        self.selected_analysts = selected_analysts

        # Set up the graph
        self.graph = self.graph_setup.setup_graph(selected_analysts)

    def _get_provider_kwargs(self) -> Dict[str, Any]:
        """Get provider-specific kwargs for LLM client creation."""
        kwargs = {}
        provider = self.config.get("llm_provider", "").lower()

        if provider == "google":
            thinking_level = self.config.get("google_thinking_level")
            if thinking_level:
                kwargs["thinking_level"] = thinking_level

        elif provider == "openai":
            reasoning_effort = self.config.get("openai_reasoning_effort")
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort

        elif provider == "anthropic":
            effort = self.config.get("anthropic_effort")
            if effort:
                kwargs["effort"] = effort

        return kwargs

    def _create_tool_nodes(self) -> Dict[str, ToolNode]:
        """Create tool nodes for different data sources using abstract methods."""
        return {
            "market": ToolNode(
                [
                    # Core stock data tools
                    get_stock_data,
                    # Technical indicators
                    get_indicators,
                ]
            ),
            "social": ToolNode(
                [
                    # News tools for social media analysis
                    get_news,
                ]
            ),
            "news": ToolNode(
                [
                    # News and insider information
                    get_news,
                    get_global_news,
                    get_insider_transactions,
                ]
            ),
            "fundamentals": ToolNode(
                [
                    # Fundamental analysis tools
                    get_fundamentals,
                    get_balance_sheet,
                    get_cashflow,
                    get_income_statement,
                    get_sebi_filings,
                    get_bulk_block_deals,
                ]
            ),
            "small_cap": ToolNode(
                [
                    # Small Cap and PSU tools
                    get_news,
                    get_government_tenders,
                ]
            ),
        }

    # ------------------------------------------------------------------
    # Per-analyst LLM helpers
    # ------------------------------------------------------------------

    _ANALYST_REPORT_FIELD = {
        "market": "market_report",
        "social": "sentiment_report",
        "news": "news_report",
        "fundamentals": "fundamentals_report",
        "small_cap": "small_cap_report",
    }

    def _build_analyst_llm(self, analyst_type: str):
        """Return an LLM for *analyst_type*, using per-analyst config when present."""
        llm_map = self.config.get("analyst_llm_map", {})
        if analyst_type not in llm_map:
            return self.quick_thinking_llm

        cfg = llm_map[analyst_type]
        llm_kwargs = self._get_provider_kwargs()
        if self.callbacks:
            llm_kwargs["callbacks"] = self.callbacks

        client = create_llm_client(
            provider=cfg.get("provider", self.config["llm_provider"]),
            model=cfg.get("model", self.config["quick_think_llm"]),
            base_url=cfg.get("base_url", self.config.get("backend_url")),
            **llm_kwargs,
        )
        return client.get_llm()

    # ------------------------------------------------------------------
    # Unified streaming entry-point (used by the web UI)
    # ------------------------------------------------------------------

    def stream_analysis(self, company_name: str, trade_date: str):
        """Yield state-chunks as analysis progresses.

        Routes to parallel or sequential mode based on config["parallel_analysts"].
        Compatible with the same chunk-dict interface as graph.graph.stream().
        """
        self.ticker = company_name
        session_id = generate_session_id()
        execution_timestamp = get_execution_timestamp()

        if self.config.get("parallel_analysts", False):
            yield from self._stream_parallel(company_name, trade_date, session_id, execution_timestamp)
        else:
            yield from self._stream_sequential(company_name, trade_date, session_id, execution_timestamp)

    def _stream_sequential(self, company_name, trade_date, session_id, execution_timestamp):
        """Original single-graph streaming path."""
        init_state = self.propagator.create_initial_state(company_name, trade_date)
        init_state["session_id"] = session_id
        init_state["execution_timestamp"] = execution_timestamp
        init_state["data_sources"] = {}

        args = self.propagator.get_graph_args()
        captured = {}
        token = data_sources_var.set({})
        try:
            final_state = None
            for chunk in self.graph.stream(init_state, **args):
                chunk["session_id"] = session_id
                chunk["execution_timestamp"] = execution_timestamp
                final_state = chunk
                # Set curr_state as soon as the final decision arrives so the web UI
                # can read session_id / execution_timestamp inside the loop.
                if chunk.get("final_trade_decision"):
                    captured = data_sources_var.get()
                    chunk["data_sources"] = captured
                    self.curr_state = chunk
                yield chunk
        finally:
            captured = data_sources_var.get()
            data_sources_var.reset(token)

        if final_state:
            final_state["data_sources"] = captured or {}
            self.curr_state = final_state
            self._log_state(trade_date, final_state)

    def _stream_parallel(self, company_name, trade_date, session_id, execution_timestamp):
        """Run all analysts concurrently, then stream the debate/PM phase."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        all_reports: dict = {}
        all_data_sources: dict = {}

        def _run_analyst(analyst_type: str):
            llm = self._build_analyst_llm(analyst_type)
            mini_graph = self.graph_setup.setup_analyst_graph(analyst_type, llm)
            init_state = self.propagator.create_initial_state(company_name, trade_date)
            token = data_sources_var.set({})
            try:
                result = mini_graph.invoke(
                    init_state,
                    config={"recursion_limit": self.config.get("max_recur_limit", 100)},
                )
            finally:
                captured = data_sources_var.get()
                data_sources_var.reset(token)
            return analyst_type, result, captured

        with ThreadPoolExecutor(max_workers=len(self.selected_analysts)) as pool:
            futures = {pool.submit(_run_analyst, a): a for a in self.selected_analysts}
            for future in as_completed(futures):
                analyst_type, state, captured = future.result()
                field = self._ANALYST_REPORT_FIELD.get(analyst_type)
                if field:
                    all_reports[field] = state.get(field, "")
                all_data_sources.update(captured)
                # Yield immediately so the web UI renders each report as it arrives.
                yield {
                    **all_reports,
                    "session_id": session_id,
                    "execution_timestamp": execution_timestamp,
                }

        # Build initial state for debate phase with all analyst reports pre-filled.
        debate_init = self.propagator.create_initial_state(company_name, trade_date)
        debate_init.update(all_reports)
        debate_init["session_id"] = session_id
        debate_init["execution_timestamp"] = execution_timestamp
        debate_init["data_sources"] = all_data_sources

        debate_graph = self.graph_setup.setup_debate_graph()
        token = data_sources_var.set(dict(all_data_sources))
        try:
            final_state = None
            for chunk in debate_graph.stream(
                debate_init,
                stream_mode="values",
                config={"recursion_limit": self.config.get("max_recur_limit", 100)},
            ):
                merged = {**all_reports, **chunk, "session_id": session_id, "execution_timestamp": execution_timestamp}
                final_state = merged
                # Set curr_state as soon as the final decision arrives so the web UI
                # can read session_id / execution_timestamp inside the loop.
                if merged.get("final_trade_decision"):
                    merged["data_sources"] = all_data_sources
                    self.curr_state = merged
                yield merged
        finally:
            extra = data_sources_var.get()
            data_sources_var.reset(token)
            all_data_sources.update(extra)

        if final_state:
            final_state["data_sources"] = all_data_sources
            self.curr_state = final_state
            self._log_state(trade_date, final_state)

    # ------------------------------------------------------------------
    # MCP / batch propagation (unchanged interface)
    # ------------------------------------------------------------------

    def propagate(self, company_name, trade_date):
        """Run the trading agents graph for a company on a specific date."""

        self.ticker = company_name
        session_id = generate_session_id()
        execution_timestamp = get_execution_timestamp()

        if self.config.get("parallel_analysts", False):
            final_state = self._propagate_parallel(company_name, trade_date, session_id, execution_timestamp)
        else:
            final_state = self._propagate_sequential(company_name, trade_date, session_id, execution_timestamp)

        self.curr_state = final_state
        self._log_state(trade_date, final_state)
        return final_state, self.process_signal(final_state["final_trade_decision"])

    def _propagate_sequential(self, company_name, trade_date, session_id, execution_timestamp):
        """Original single-graph invoke path."""
        init_agent_state = self.propagator.create_initial_state(company_name, trade_date)
        init_agent_state["session_id"] = session_id
        init_agent_state["execution_timestamp"] = execution_timestamp
        init_agent_state["data_sources"] = {}

        args = self.propagator.get_graph_args()
        token = data_sources_var.set({})
        try:
            if self.debug:
                trace = []
                for chunk in self.graph.stream(init_agent_state, **args):
                    if chunk.get("messages"):
                        chunk["messages"][-1].pretty_print()
                        trace.append(chunk)
                final_state = trace[-1]
            else:
                final_state = self.graph.invoke(init_agent_state, **args)
        finally:
            captured_sources = data_sources_var.get()
            data_sources_var.reset(token)

        final_state["session_id"] = session_id
        final_state["execution_timestamp"] = execution_timestamp
        final_state["data_sources"] = captured_sources or {}
        return final_state

    def _propagate_parallel(self, company_name, trade_date, session_id, execution_timestamp):
        """Run all analysts in parallel, then invoke debate/PM."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        all_reports: dict = {}
        all_data_sources: dict = {}

        def _run_analyst(analyst_type: str):
            llm = self._build_analyst_llm(analyst_type)
            mini_graph = self.graph_setup.setup_analyst_graph(analyst_type, llm)
            init_state = self.propagator.create_initial_state(company_name, trade_date)
            token = data_sources_var.set({})
            try:
                result = mini_graph.invoke(
                    init_state,
                    config={"recursion_limit": self.config.get("max_recur_limit", 100)},
                )
            finally:
                captured = data_sources_var.get()
                data_sources_var.reset(token)
            return analyst_type, result, captured

        with ThreadPoolExecutor(max_workers=len(self.selected_analysts)) as pool:
            futures = {pool.submit(_run_analyst, a): a for a in self.selected_analysts}
            for future in as_completed(futures):
                analyst_type, state, captured = future.result()
                field = self._ANALYST_REPORT_FIELD.get(analyst_type)
                if field:
                    all_reports[field] = state.get(field, "")
                all_data_sources.update(captured)

        debate_init = self.propagator.create_initial_state(company_name, trade_date)
        debate_init.update(all_reports)
        debate_init["session_id"] = session_id
        debate_init["execution_timestamp"] = execution_timestamp
        debate_init["data_sources"] = all_data_sources

        debate_graph = self.graph_setup.setup_debate_graph()
        token = data_sources_var.set(dict(all_data_sources))
        try:
            final_state = debate_graph.invoke(
                debate_init,
                config={"recursion_limit": self.config.get("max_recur_limit", 100)},
            )
        finally:
            extra = data_sources_var.get()
            data_sources_var.reset(token)
            all_data_sources.update(extra)

        final_state.update(all_reports)
        final_state["session_id"] = session_id
        final_state["execution_timestamp"] = execution_timestamp
        final_state["data_sources"] = all_data_sources
        return final_state

    def _log_state(self, trade_date, final_state):
        """Log the final state to a JSON file and cryptographic audit trail."""
        self.log_states_dict[str(trade_date)] = {
            "company_of_interest": final_state["company_of_interest"],
            "trade_date": final_state["trade_date"],
            "session_id": final_state.get("session_id", ""),
            "execution_timestamp": final_state.get("execution_timestamp", ""),
            "data_sources": final_state.get("data_sources", {}),
            "market_report": final_state.get("market_report", ""),
            "sentiment_report": final_state.get("sentiment_report", ""),
            "news_report": final_state.get("news_report", ""),
            "fundamentals_report": final_state.get("fundamentals_report", ""),
            "small_cap_report": final_state.get("small_cap_report", ""),
            "investment_debate_state": {
                "bull_history": final_state["investment_debate_state"]["bull_history"],
                "bear_history": final_state["investment_debate_state"]["bear_history"],
                "history": final_state["investment_debate_state"]["history"],
                "current_response": final_state["investment_debate_state"][
                    "current_response"
                ],
                "judge_decision": final_state["investment_debate_state"][
                    "judge_decision"
                ],
            },
            "trader_investment_decision": final_state["trader_investment_plan"],
            "risk_debate_state": {
                "aggressive_history": final_state["risk_debate_state"]["aggressive_history"],
                "conservative_history": final_state["risk_debate_state"]["conservative_history"],
                "neutral_history": final_state["risk_debate_state"]["neutral_history"],
                "history": final_state["risk_debate_state"]["history"],
                "judge_decision": final_state["risk_debate_state"]["judge_decision"],
            },
            "investment_plan": final_state["investment_plan"],
            "final_trade_decision": final_state["final_trade_decision"],
        }

        # Save to file
        directory = Path(self.config["results_dir"]) / self.ticker / "OrbisQuantAgentsStrategy_logs"
        directory.mkdir(parents=True, exist_ok=True)

        log_path = directory / f"full_states_log_{trade_date}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(self.log_states_dict[str(trade_date)], f, indent=4)

        # Save to append-only cryptographically chained audit log
        append_audit_log(
            ticker=self.ticker,
            trade_date=str(trade_date),
            log_entry=self.log_states_dict[str(trade_date)],
            results_dir=self.config["results_dir"]
        )

    def reflect_and_remember(self, returns_losses):
        """Reflect on decisions and update memory based on returns."""
        self.reflector.reflect_bull_researcher(
            self.curr_state, returns_losses, self.bull_memory
        )
        self.reflector.reflect_bear_researcher(
            self.curr_state, returns_losses, self.bear_memory
        )
        self.reflector.reflect_trader(
            self.curr_state, returns_losses, self.trader_memory
        )
        self.reflector.reflect_invest_judge(
            self.curr_state, returns_losses, self.invest_judge_memory
        )
        self.reflector.reflect_portfolio_manager(
            self.curr_state, returns_losses, self.portfolio_manager_memory
        )

    def process_signal(self, full_signal):
        """Process a signal to extract the core decision."""
        return self.signal_processor.process_signal(full_signal)
