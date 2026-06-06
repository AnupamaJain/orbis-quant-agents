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
import logging
import os
from datetime import date, datetime
from typing import Optional
from uuid import UUID

import time
from starlette.datastructures import Headers, QueryParams
from starlette.requests import Request
from starlette.responses import JSONResponse
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("orbis-quant-mcp")

load_dotenv()

# ── Security & Authentication ASGI Middleware ─────────────────────────────────

class SecureASGIMiddleware:
    """ASGI middleware providing API key auth, rate limiting, and SSE session-readiness gating."""

    def __init__(self, app, calls_per_minute: int = 30, sse_transport=None):
        self.app = app
        self.calls_per_minute = calls_per_minute
        self.requests = {}
        # Reference to SseServerTransport so we can check session readiness
        self._sse_transport = sse_transport

    async def __call__(self, scope, receive, send):
        # We only apply protection to HTTP requests
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        query_params = QueryParams(scope.get("query_string", b"").decode("utf-8"))
        request_path = scope.get("path", "")

        # Health check — respond immediately, bypass all auth/rate-limiting
        if request_path == "/health" and scope.get("method") in ("GET", "HEAD"):
            provider = os.getenv("LLM_PROVIDER", "openai")
            await self._send_json_response(send, {
                "status":   "ok",
                "server":   "orbis-quant-agents",
                "provider": provider,
                "port":     int(os.getenv("MCP_PORT", "8001")),
            }, status_code=200)
            return

        # 1. API Key verification (Bypass /messages paths since they rely on the session_id handshake)
        expected_key = os.getenv("MCP_API_KEY")
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
        # ⚠️ HORIZONTAL SCALING WARNING:
        # This rate limiter uses a process-local in-memory dict (`self.requests`).
        # If the server is deployed with multiple replicas (horizontal pod scaling) or
        # multiple Uvicorn workers, each worker enforces limits independently.
        # This means the effective global limit will scale up to (N * calls_per_minute)
        # and request blocking will be distributed. For a strict centralized rate limit,
        # this should be backed by a shared datastore like Redis.
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

        # 3. Session-readiness gating for POST /messages/ requests (SSE only)
        # Instead of a blind 200ms sleep, poll until the SSE session is actually
        # registered in the transport's session map. This eliminates the
        # "Received request before initialization was complete" race condition.
        #
        # ⚠️ FRAGILITY WARNING (SDK Private Attribute):
        # We access `self._sse_transport._read_stream_writers` which is a private,
        # undocumented field inside MCP Python SDK's SseServerTransport class.
        # Upgrading the `mcp` library package might break this if internal state
        # representation changes.
        #
        # ⚠️ SCALING & ARCHITECTURE WARNING (Single-Process / Sticky Sessions):
        # This memory check is process-local. If this service is scaled to multiple
        # replica containers or run with multiple Uvicorn worker processes behind a load
        # balancer (without session pinning), incoming POST requests might route to a
        # different process than the one holding the SSE stream connection.
        # If deploying to a multi-instance/multi-worker environment, you MUST either:
        #   - Enable sticky sessions (session pinning) on your load balancer/ingress,
        #   - Force single-worker mode (default in FastMCP), or
        #   - Migrate to a stateless transport (like Streamable HTTP).
        if self._sse_transport is not None and scope.get("method") == "POST" and request_path.startswith("/messages"):
            session_id_hex = query_params.get("session_id")
            if session_id_hex:
                try:
                    sid = UUID(hex=session_id_hex)
                except ValueError:
                    sid = None

                if sid is not None:
                    # Poll up to 5 s (10 × 500 ms) for the session to appear in the local registry
                    for attempt in range(10):
                        if sid in self._sse_transport._read_stream_writers:
                            logger.debug(
                                "Session %s ready after %d ms",
                                session_id_hex, attempt * 500,
                            )
                            break
                        logger.debug(
                            "Session %s not ready, waiting (attempt %d/10)…",
                            session_id_hex, attempt + 1,
                        )
                        await asyncio.sleep(0.5)
                    else:
                        logger.warning(
                            "Session %s still not registered after 5 s — forwarding anyway",
                            session_id_hex,
                        )
            else:
                # Fallback if we don't have the transport ref or no session_id
                await asyncio.sleep(0.3)

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

        # Grab the SseServerTransport instance so the middleware can poll for
        # session readiness instead of using a blind sleep.
        sse_transport = None
        for route in app.routes:
            # The Mount at /messages/ wraps sse.handle_post_message;
            # its .app holds the transport's bound method, giving us the instance.
            if hasattr(route, "path") and "/messages" in getattr(route, "path", ""):
                handler = getattr(route, "app", None)
                if handler is not None and hasattr(handler, "__self__"):
                    sse_transport = handler.__self__
                    break

        # Register our secure middleware inside Starlette's middleware stack (Inner layer)
        rate_limit = int(os.getenv("MCP_RATE_LIMIT", "30"))
        app.add_middleware(
            SecureASGIMiddleware,
            calls_per_minute=rate_limit,
            sse_transport=sse_transport,
        )

        # Add CORS support (Outer layer - added last for LIFO execution order)
        # Note: allow_credentials must be False when allow_origins is "*"
        from starlette.middleware.cors import CORSMiddleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Restrict this to your Vercel domains in production
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        if sse_transport:
            logger.info("SSE transport reference acquired — session-readiness polling enabled")
        else:
            logger.warning(
                "Could not acquire SSE transport reference — falling back to fixed delay. "
                "This may happen if the Starlette route layout changed."
            )

        return app

    def streamable_http_app(self):
        # Get the standard FastMCP Starlette app
        app = super().streamable_http_app()

        # Register our secure middleware inside Starlette's middleware stack (Inner layer)
        rate_limit = int(os.getenv("MCP_RATE_LIMIT", "30"))
        app.add_middleware(
            SecureASGIMiddleware,
            calls_per_minute=rate_limit,
            sse_transport=None,
        )

        # Add CORS support (Outer layer - added last for LIFO execution order)
        # Note: allow_credentials must be False when allow_origins is "*"
        from starlette.middleware.cors import CORSMiddleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Restrict this to your Vercel domains in production
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        return app



# ── Server setup ─────────────────────────────────────────────────────────────

_PORT = int(os.getenv("MCP_PORT", "8001"))

# Determine transport and configure stateless HTTP for scaling
_transport = "stdio"
if "--transport" in sys.argv:
    idx = sys.argv.index("--transport")
    _transport = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "stdio"

is_stateless = (_transport == "streamable-http")

mcp = SecureFastMCP(
    name="orbis-quant-agents",
    host="0.0.0.0",
    port=_PORT,
    stateless_http=is_stateless,
    json_response=is_stateless,
    instructions=(
        "Multi-agent quantitative analysis for Indian stock markets (NSE/BSE). "
        "Runs Technical, Fundamental, Sentiment and News agents followed by a "
        "Bullish vs Bearish research debate and a Portfolio Manager decision. "
        "Use analyze_stock for full pipeline. Use individual tools for faster, "
        "targeted queries."
    ),
)



# ── Health endpoint (registered via FastMCP custom_route) ─────────────────────

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Liveness / readiness probe for load-balancers and monitoring."""
    provider = os.getenv("LLM_PROVIDER", "openai")
    return JSONResponse({
        "status":   "ok",
        "server":   "orbis-quant-agents",
        "provider": provider,
        "port":     _PORT,
    })


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

def _run_pipeline(symbol: str, trade_date: str, analyst_list: list[str]) -> dict:
    """Synchronous helper — runs the blocking graph pipeline."""
    graph = _get_graph(analyst_list)
    final_state, decision = graph.propagate(symbol, trade_date)
    return {
        "symbol":     symbol,
        "trade_date": trade_date,
        "analysts":   analyst_list,
        "decision":   decision,
        "status":     "success",
    }


@mcp.tool()
async def analyze_stock(
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
        # Run the blocking graph pipeline in a thread so the async event loop
        # stays free for SSE heartbeats and other concurrent requests.
        result = await asyncio.to_thread(_run_pipeline, symbol, trade_date, analyst_list)
        return json.dumps(result, indent=2, default=str)

    except Exception as e:
        provider = os.getenv("LLM_PROVIDER", "openai")
        model    = os.getenv("DEEP_THINK_LLM", "unknown")
        logger.exception("analyze_stock failed for %s", symbol)
        return json.dumps({
            "symbol":   symbol,
            "status":   "error",
            "message":  str(e),
            "provider": provider,
            "model":    model,
            "hint":     (
                f"Check that the {provider.upper()} API key is set and valid. "
                f"Current provider={provider}, model={model}."
            ),
        })


@mcp.tool()
async def get_technical_analysis(symbol: str) -> str:
    """
    Run only the technical analyst agent — fast, no fundamental or news data needed.

    Returns Camarilla pivot levels, trend direction, RSI, MACD, support/resistance.
    Useful for quick pre-market setup validation.

    Args:
        symbol: NSE ticker (e.g. "RELIANCE", "TCS"). .NS suffix added automatically.
    """
    return await analyze_stock(symbol=symbol, analysts="market")


@mcp.tool()
async def get_fundamental_analysis(symbol: str) -> str:
    """
    Run only the fundamental analyst agent.

    Returns PE ratio, EPS trend, revenue growth, debt levels, promoter holding,
    FII/DII ownership, and valuation vs sector peers.

    Args:
        symbol: NSE ticker (e.g. "HDFCBANK", "WIPRO"). .NS suffix added automatically.
    """
    return await analyze_stock(symbol=symbol, analysts="fundamentals")


@mcp.tool()
async def get_sentiment_analysis(symbol: str) -> str:
    """
    Run sentiment + news agents — no technical or fundamental data.

    Returns recent news sentiment score, social media tone, key headlines,
    SEBI filings/announcements, and institutional flow signals.

    Args:
        symbol: NSE ticker.
    """
    return await analyze_stock(symbol=symbol, analysts="social,news")


@mcp.tool()
async def debate_trade(symbol: str, trade_date: Optional[str] = None) -> str:
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
    return await analyze_stock(symbol=symbol, trade_date=trade_date,
                               analysts="market,fundamentals,social,news")


@mcp.tool()
async def screen_watchlist(symbols: str, trade_date: Optional[str] = None) -> str:
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
            raw = await analyze_stock(symbol=sym, trade_date=trade_date, analysts="market")
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
    elif transport == "streamable-http":
        print(f"Starting Orbis Quant Agents MCP server (Streamable HTTP) on port {_PORT}…")
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
