"""
Orbis Quant Agents — MCP Server

Exposes the multi-agent analysis pipeline as MCP tools so any MCP client
(Claude Code, Claude Desktop, or the Orbis trading terminal) can run
full AI-powered stock analysis with a single tool call.

Usage:
  python mcp/mcp_server.py                     # stdio transport (Claude Code)
  python mcp/mcp_server.py --transport sse     # SSE transport (HTTP clients)

Register in Claude Code (.claude/settings.json):
  {
    "mcpServers": {
      "orbis-quant-agents": {
        "command": "python",
        "args": ["/path/to/orbis-quant-agents/mcp/mcp_server.py"]
      }
    }
  }
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import asyncio
import json
import os
from datetime import date, datetime
from typing import Optional

import time
from starlette.datastructures import Headers, QueryParams
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

# ── Security & Authentication ASGI Middleware ─────────────────────────────────

class SecureASGIMiddleware:
    def __init__(self, app, calls_per_minute: int = 30):
        self.app = app
        self.calls_per_minute = calls_per_minute
        self.requests = {}

    async def __call__(self, scope, receive, send):
        # We only apply protection to HTTP requests
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        query_params = QueryParams(scope.get("query_string", b"").decode("utf-8"))

        # 1. API Key verification (Bypass /messages paths since they rely on the session_id handshake)
        expected_key = os.getenv("MCP_API_KEY")
        request_path = scope.get("path", "")
        if expected_key and not request_path.startswith("/messages"):
            # Check custom headers and Authorization header
            api_key = headers.get("x-api-key")
            if not api_key:
                auth_header = headers.get("authorization")
                if auth_header and auth_header.startswith("Bearer "):
                    api_key = auth_header[7:]
            # Check query parameters as a fallback
            if not api_key:
                api_key = query_params.get("api_key")

            if api_key != expected_key:
                await self._send_json_response(
                    send, 
                    {"status": "error", "message": "Unauthorized: Invalid or missing API key."}, 
                    status_code=401
                )
                return

        # 2. Rate Limiting by Client IP
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"
        now = time.time()

        if client_ip in self.requests:
            self.requests[client_ip] = [t for t in self.requests[client_ip] if now - t < 60]
        else:
            self.requests[client_ip] = []

        if len(self.requests[client_ip]) >= self.calls_per_minute:
            await self._send_json_response(
                send, 
                {"status": "error", "message": "Too Many Requests: Rate limit exceeded."}, 
                status_code=429
            )
            return

        self.requests[client_ip].append(now)

        # 3. Handle Concurrency Race Condition
        # Delay incoming POST messages by 200ms to allow the GET /sse connection 
        # background thread to finish setting up the session session-manager.
        if scope.get("method") == "POST" and request_path.startswith("/messages"):
            await asyncio.sleep(0.2)

        # Delegate execution downstream
        await self.app(scope, receive, send)

    async def _send_json_response(self, send, data: dict, status_code: int):
        body = json.dumps(data).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": status_code,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("utf-8")),
            ]
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })


class SecureFastMCP(FastMCP):
    def sse_app(self, mount_path: str | None = None):
        # Get the standard FastMCP Starlette app
        app = super().sse_app(mount_path)
        
        # Add CORS support so your Vercel frontend can call this EC2 backend
        from starlette.middleware.cors import CORSMiddleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Restrict this to your Vercel domains in production
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Register our secure middleware inside Starlette's middleware stack
        # This keeps the app type as Starlette so Uvicorn can run the lifespan/startup events correctly
        rate_limit = int(os.getenv("MCP_RATE_LIMIT", "30"))
        app.add_middleware(SecureASGIMiddleware, calls_per_minute=rate_limit)
        
        return app


# ── Server setup ─────────────────────────────────────────────────────────────

_PORT = int(os.getenv("MCP_PORT", "8001"))

mcp = SecureFastMCP(
    name="orbis-quant-agents",
    host="0.0.0.0",
    port=_PORT,
    instructions=(
        "Multi-agent quantitative analysis for Indian stock markets (NSE/BSE). "
        "Runs Technical, Fundamental, Sentiment and News agents followed by a "
        "Bullish vs Bearish research debate and a Portfolio Manager decision. "
        "Use analyze_stock for full pipeline. Use individual tools for faster, "
        "targeted queries."
    ),
)


# Lazy-init the graph so import doesn't block server startup
_graph_instances = {}

def _get_graph(analysts=None):
    global _graph_instances
    analyst_list = analysts or ["market", "social", "news", "fundamentals"]
    analyst_tuple = tuple(sorted(analyst_list))
    
    if analyst_tuple not in _graph_instances:
        from orbisquantagents.graph.orbis_quant_graph import OrbisQuantAgentsGraph
        from orbisquantagents.default_config import DEFAULT_CONFIG

        cfg = DEFAULT_CONFIG.copy()
        cfg["deep_think_llm"]  = os.getenv("DEEP_THINK_LLM",  cfg["deep_think_llm"])
        cfg["quick_think_llm"] = os.getenv("QUICK_THINK_LLM", cfg["quick_think_llm"])
        cfg["llm_provider"]    = os.getenv("LLM_PROVIDER",    cfg["llm_provider"])
        cfg["max_debate_rounds"] = 1

        _graph_instances[analyst_tuple] = OrbisQuantAgentsGraph(
            selected_analysts=analyst_list,
            debug=False,
            config=cfg,
        )
    return _graph_instances[analyst_tuple]


# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def analyze_stock(
    symbol: str,
    trade_date: Optional[str] = None,
    analysts: Optional[str] = "market,social,news,fundamentals",
) -> str:
    """
    Run the full Orbis multi-agent analysis pipeline on a stock.

    Agents run in sequence:
      1. Technical analyst  — price action, Camarilla levels, trend
      2. Fundamental analyst — PE, EPS, revenue, promoter holding
      3. Sentiment analyst  — news tone, social, FII/DII flows
      4. News analyst       — recent events, SEBI filings
      5. Bullish researcher — makes the bull case
      6. Bearish researcher — makes the bear case
      7. Portfolio manager  — final verdict: BUY / SELL / HOLD + confidence

    Args:
        symbol:     NSE/BSE ticker (e.g. "RELIANCE.NS", "INFY.NS"). Append .NS for NSE.
        trade_date: Analysis date as YYYY-MM-DD. Defaults to today.
        analysts:   Comma-separated analyst types to include.
                    Options: market, social, news, fundamentals
                    Default: all four.

    Returns:
        JSON string with full analysis including final decision and confidence score.
    """
    if not symbol.endswith((".NS", ".BO")):
        symbol = symbol.upper() + ".NS"

    if trade_date is None:
        trade_date = date.today().strftime("%Y-%m-%d")

    analyst_list = [a.strip() for a in analysts.split(",")]

    try:
        graph = _get_graph(analyst_list)
        final_state, decision = graph.propagate(symbol, trade_date)

        return json.dumps({
            "symbol":     symbol,
            "trade_date": trade_date,
            "analysts":   analyst_list,
            "decision":   decision,
            "status":     "success",
        }, indent=2, default=str)

    except Exception as e:
        return json.dumps({
            "symbol":  symbol,
            "status":  "error",
            "message": str(e),
        })


@mcp.tool()
def get_technical_analysis(symbol: str) -> str:
    """
    Run only the technical analyst agent — fast, no fundamental or news data needed.

    Returns Camarilla pivot levels, trend direction, RSI, MACD, support/resistance.
    Useful for quick pre-market setup validation.

    Args:
        symbol: NSE ticker (e.g. "RELIANCE", "TCS"). .NS suffix added automatically.
    """
    return analyze_stock(symbol=symbol, analysts="market")


@mcp.tool()
def get_fundamental_analysis(symbol: str) -> str:
    """
    Run only the fundamental analyst agent.

    Returns PE ratio, EPS trend, revenue growth, debt levels, promoter holding,
    FII/DII ownership, and valuation vs sector peers.

    Args:
        symbol: NSE ticker (e.g. "HDFCBANK", "WIPRO"). .NS suffix added automatically.
    """
    return analyze_stock(symbol=symbol, analysts="fundamentals")


@mcp.tool()
def get_sentiment_analysis(symbol: str) -> str:
    """
    Run sentiment + news agents — no technical or fundamental data.

    Returns recent news sentiment score, social media tone, key headlines,
    SEBI filings/announcements, and institutional flow signals.

    Args:
        symbol: NSE ticker.
    """
    return analyze_stock(symbol=symbol, analysts="social,news")


@mcp.tool()
def debate_trade(symbol: str, trade_date: Optional[str] = None) -> str:
    """
    Run the full bull vs bear research debate for a stock.

    Includes:
      - Bullish researcher: best-case thesis with supporting evidence
      - Bearish researcher: counter-arguments and risk factors
      - Portfolio manager: final risk-adjusted verdict

    Best used when you want a balanced view before committing to a position.

    Args:
        symbol:     NSE ticker.
        trade_date: YYYY-MM-DD. Defaults to today.
    """
    return analyze_stock(symbol=symbol, trade_date=trade_date,
                         analysts="market,fundamentals,social,news")


@mcp.tool()
def screen_watchlist(symbols: str, trade_date: Optional[str] = None) -> str:
    """
    Run quick technical analysis on a list of stocks and rank by signal strength.

    Useful for screening the pre-market watchlist before trading begins.
    Runs the market (technical) agent only for speed — full analysis on top picks.

    Args:
        symbols:    Comma-separated NSE tickers (e.g. "RELIANCE,TCS,INFY,WIPRO").
        trade_date: YYYY-MM-DD. Defaults to today.

    Returns:
        JSON array of stocks ranked by signal confidence, with brief analysis each.
    """
    ticker_list = [s.strip().upper() for s in symbols.split(",")]
    results = []

    for sym in ticker_list:
        try:
            raw = analyze_stock(symbol=sym, trade_date=trade_date, analysts="market")
            data = json.loads(raw)
            results.append({
                "symbol":   sym,
                "status":   data.get("status"),
                "decision": data.get("decision", {}).get("decision", "UNKNOWN"),
                "confidence": data.get("decision", {}).get("confidence", 0),
            })
        except Exception as e:
            results.append({"symbol": sym, "status": "error", "error": str(e)})

    # Rank by confidence descending
    results.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    return json.dumps(results, indent=2)


# ── Resources ─────────────────────────────────────────────────────────────────

@mcp.resource("config://agents")
def get_agent_config() -> str:
    """Current agent configuration including LLM provider and analyst selection."""
    from orbisquantagents.default_config import DEFAULT_CONFIG
    cfg = {k: v for k, v in DEFAULT_CONFIG.items()
           if k not in ("project_dir", "results_dir", "data_cache_dir")}
    cfg["llm_provider"] = os.getenv("LLM_PROVIDER", cfg["llm_provider"])
    cfg["deep_think_llm"] = os.getenv("DEEP_THINK_LLM", cfg["deep_think_llm"])
    return json.dumps(cfg, indent=2)


@mcp.resource("analysts://available")
def list_analysts() -> str:
    """Lists all available analyst types and what each one analyses."""
    return json.dumps({
        "market":       "Technical analysis: price action, Camarilla, RSI, MACD, trend",
        "fundamentals": "PE, EPS, revenue, promoter holding, FII/DII, valuation",
        "social":       "Social media sentiment, retail investor tone",
        "news":         "Recent headlines, SEBI filings, corporate events",
    }, indent=2)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    transport = "stdio"
    if "--transport" in sys.argv:
        idx = sys.argv.index("--transport")
        transport = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "stdio"

    if transport == "sse":
        print(f"Starting Orbis Quant Agents MCP server (SSE) on port {_PORT}…")
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")
