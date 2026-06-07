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
import warnings
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
from starlette.responses import JSONResponse, HTMLResponse
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP, Context

# ── Logging configuration ─────────────────────────────────────────────────────
# Keep our own logger at INFO; silence noisy third-party libraries that would
# otherwise flood Railway's 500 log/s limit with per-request HTTP traces and
# repeated pandas deprecation warnings.
logging.basicConfig(level=logging.WARNING)
logging.getLogger("orbis-quant-mcp").setLevel(logging.INFO)

# httpx / httpcore log one line per LLM HTTP call — at INFO that's hundreds of
# lines per analysis run.  WARNING keeps connection errors visible.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Uvicorn access log prints every POST /mcp — useful locally, too noisy in prod.
logging.getLogger("uvicorn.access").setLevel(
    logging.WARNING if os.getenv("RAILWAY_ENVIRONMENT") else logging.INFO
)

# Suppress the pandas Timestamp.utcnow deprecation warning that fires on every
# data fetch call.
warnings.filterwarnings("ignore", message=".*utcnow.*deprecated.*", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*Timestamp.utcnow.*", category=FutureWarning)

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

        # /connect is a public onboarding page — no auth required
        if request_path == "/connect" and scope.get("method") in ("GET", "HEAD"):
            await self.app(scope, receive, send)
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
    json_response=False,   # stream SSE so Railway's 120s HTTP timeout never fires
    instructions=(
        "You are Orbis Quant, an AI-powered stock analyst for Indian markets (NSE/BSE).\n\n"
        "ALWAYS follow this staged workflow — never call analyze_stock directly as the first step:\n"
        "1. Call get_price_snapshot(symbol) first — returns live price, PE, volume in ~2 seconds. "
        "Narrate what you see: price trend, how volume compares to average, valuation vs sector.\n"
        "2. Call get_technical_analysis(symbol) — RSI, MACD, support/resistance. "
        "After it returns, explain what the chart is saying in plain English.\n"
        "3. Call get_fundamental_analysis(symbol) if the user wants depth — PE, EPS, promoter holding. "
        "Comment on whether the valuation is attractive.\n"
        "4. Call get_sentiment_analysis(symbol) if relevant — news tone, FII/DII flows. "
        "Highlight the most important recent development.\n"
        "5. Call debate_trade(symbol) for the full bull/bear debate and final BUY/SELL/HOLD verdict. "
        "Present the verdict clearly with your own view.\n\n"
        "For quick pre-market checks or watchlist screening, use get_technical_analysis or "
        "screen_watchlist directly — no need for the full 5-step flow.\n\n"
        "Speak like a seasoned analyst: direct, specific, no filler. "
        "Always quote the actual numbers from tool results."
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


_CONNECT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Connect — Orbis Quant Agents</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:        #F5F1EB;
    --surface:   #FDFCFA;
    --border:    #E8E3DB;
    --border-med:#D4CEC5;
    --text:      #1A1714;
    --text-2:    #6B6560;
    --text-3:    #9B9590;
    --accent:    #D97757;
    --accent-dk: #C4623E;
    --accent-bg: #FDF0EB;
    --accent-bd: #F5C9B7;
    --code-bg:   #EDE8E0;
    --shadow-sm: 0 1px 3px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04);
    --shadow:    0 4px 12px rgba(0,0,0,.07), 0 1px 3px rgba(0,0,0,.05);
    --radius:    14px;
    --radius-sm: 8px;
  }

  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    padding: 48px 20px 80px;
    -webkit-font-smoothing: antialiased;
  }

  .wrap { max-width: 660px; margin: 0 auto; }

  /* ── Header ── */
  .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 52px; }
  .logo   { display: flex; align-items: center; gap: 11px; }
  .logo-mark {
    width: 36px; height: 36px;
    background: var(--accent);
    border-radius: 9px;
    display: flex; align-items: center; justify-content: center;
    font-size: 17px;
    box-shadow: 0 2px 8px rgba(217,119,87,.30);
  }
  .logo-name { font-size: 15px; font-weight: 700; letter-spacing: -0.2px; color: var(--text); }
  .logo-sub  { font-size: 11px; color: var(--text-3); margin-top: 1px; font-weight: 500; letter-spacing: 0.02em; }
  .status-pill {
    display: flex; align-items: center; gap: 6px;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 20px; padding: 5px 12px 5px 10px;
    font-size: 12px; color: var(--text-2); font-weight: 500;
    box-shadow: var(--shadow-sm);
  }
  .status-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: #3B9E6D;
    box-shadow: 0 0 0 2px rgba(59,158,109,.18);
    animation: pulse 2.5s ease infinite;
  }
  @keyframes pulse {
    0%,100% { box-shadow: 0 0 0 2px rgba(59,158,109,.18); }
    50%      { box-shadow: 0 0 0 4px rgba(59,158,109,.10); }
  }

  /* ── Hero ── */
  .hero { margin-bottom: 36px; }
  .hero h1 {
    font-size: 30px; font-weight: 700; letter-spacing: -0.6px;
    line-height: 1.18; margin-bottom: 10px;
    color: var(--text);
  }
  .hero p {
    font-size: 15px; color: var(--text-2); line-height: 1.6;
  }

  /* ── Cards ── */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 28px 28px 24px;
    margin-bottom: 16px;
    box-shadow: var(--shadow-sm);
  }
  .card-label {
    font-size: 11px; font-weight: 600; color: var(--accent);
    letter-spacing: 0.08em; text-transform: uppercase;
    margin-bottom: 18px;
  }

  /* ── API key + URL ── */
  .key-input {
    width: 100%; background: var(--bg);
    border: 1.5px solid var(--border-med);
    border-radius: var(--radius-sm);
    padding: 10px 14px; font-size: 14px;
    font-family: 'Inter', monospace; color: var(--text);
    outline: none; transition: border-color .18s, box-shadow .18s;
    margin-bottom: 10px;
  }
  .key-input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(217,119,87,.12); }
  .key-input::placeholder { color: var(--text-3); }

  .url-row {
    display: flex; align-items: stretch; gap: 8px;
  }
  .url-box {
    flex: 1; background: var(--code-bg);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 10px 14px;
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 12.5px; color: #6B3D2E;
    word-break: break-all; line-height: 1.55;
    min-width: 0;
  }
  .url-box .placeholder { color: var(--accent); font-weight: 600; }
  .copy-btn {
    flex-shrink: 0;
    background: var(--accent); color: #fff;
    border: none; border-radius: var(--radius-sm);
    padding: 0 16px; font-size: 13px; font-weight: 600;
    cursor: pointer; transition: background .15s, transform .1s;
    font-family: 'Inter', sans-serif;
    box-shadow: 0 1px 3px rgba(217,119,87,.25);
  }
  .copy-btn:hover   { background: var(--accent-dk); }
  .copy-btn:active  { transform: scale(.97); }
  .copy-btn.copied  { background: #3B9E6D; }
  .hint { font-size: 12px; color: var(--text-3); margin-top: 8px; }

  /* ── Tabs ── */
  .tab-bar {
    display: flex; gap: 2px;
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 10px; padding: 3px;
    margin-bottom: 24px;
  }
  .tab {
    flex: 1; text-align: center;
    padding: 7px 12px;
    border-radius: 8px;
    font-size: 13px; font-weight: 500;
    cursor: pointer; color: var(--text-2);
    transition: all .15s;
    border: 1px solid transparent;
    white-space: nowrap;
  }
  .tab:hover:not(.active) { color: var(--text); }
  .tab.active {
    background: var(--surface);
    border-color: var(--border);
    color: var(--text);
    font-weight: 600;
    box-shadow: var(--shadow-sm);
  }
  .tab-panel { display: none; }
  .tab-panel.active { display: block; }

  /* ── Steps ── */
  .step { display: flex; gap: 14px; margin-bottom: 16px; align-items: flex-start; }
  .step:last-child { margin-bottom: 0; }
  .step-num {
    min-width: 24px; height: 24px;
    background: var(--accent-bg); border: 1.5px solid var(--accent-bd);
    border-radius: 50%; display: flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 700; color: var(--accent);
    flex-shrink: 0; margin-top: 1px;
  }
  .step-body { font-size: 14px; color: var(--text-2); line-height: 1.6; }
  .step-body strong { color: var(--text); font-weight: 600; }
  .step-body code {
    background: var(--code-bg); border: 1px solid var(--border-med);
    border-radius: 5px; padding: 1px 6px;
    font-size: 12.5px; color: #6B3D2E;
    font-family: 'SF Mono', 'Fira Code', monospace;
  }

  /* ── Code snippets inside steps ── */
  .snippet {
    margin-top: 10px;
    background: #1A1714;
    border-radius: var(--radius-sm);
    padding: 14px 16px;
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 12px; color: #C9C0B5; line-height: 1.7;
    overflow-x: auto;
  }
  .snippet .k { color: #D97757; }
  .snippet .s { color: #84C59A; }
  .snippet .p { color: #8BA7C9; }

  /* ── Prompts ── */
  .prompt-grid { display: flex; flex-direction: column; gap: 8px; }
  .prompt {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 12px 16px;
    font-size: 14px; color: var(--text-2); line-height: 1.5;
    cursor: pointer; transition: border-color .15s, background .15s;
    position: relative;
    padding-right: 40px;
  }
  .prompt:hover { border-color: var(--accent-bd); background: var(--accent-bg); color: var(--text); }
  .prompt::after {
    content: '↗';
    position: absolute; right: 14px; top: 50%; transform: translateY(-50%);
    font-size: 13px; color: var(--text-3);
    transition: color .15s;
  }
  .prompt:hover::after { color: var(--accent); }

  /* ── Capabilities strip ── */
  .caps { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 20px; }
  .cap {
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 20px; padding: 5px 12px;
    font-size: 12px; color: var(--text-2); font-weight: 500;
    display: flex; align-items: center; gap: 5px;
  }

  /* ── Footer ── */
  .footer {
    text-align: center; margin-top: 52px;
    font-size: 13px; color: var(--text-3);
    display: flex; align-items: center; justify-content: center; gap: 16px;
  }
  .footer a { color: var(--text-3); text-decoration: none; }
  .footer a:hover { color: var(--text-2); }
  .footer-sep { color: var(--border-med); }
</style>
</head>
<body>
<div class="wrap">

  <header class="header">
    <div class="logo">
      <div class="logo-mark">⚡</div>
      <div>
        <div class="logo-name">Orbis Quant Agents</div>
        <div class="logo-sub">NSE · BSE · Indian Markets</div>
      </div>
    </div>
    <div class="status-pill">
      <div class="status-dot"></div>
      Live
    </div>
  </header>

  <div class="hero">
    <h1>Your AI stock analyst,<br>inside Claude</h1>
    <p>Multi-agent intelligence for Indian markets — technical, fundamental,<br>
    sentiment &amp; bull/bear debate. Connect once, analyse any NSE or BSE stock.</p>
    <div class="caps">
      <span class="cap">📊 Technical Analysis</span>
      <span class="cap">📈 Fundamentals</span>
      <span class="cap">🗞 Sentiment &amp; News</span>
      <span class="cap">⚔️ Bull vs Bear Debate</span>
      <span class="cap">⚡ Live Price Snapshots</span>
    </div>
  </div>

  <!-- ── Step 1: API Key ── -->
  <div class="card">
    <div class="card-label">Step 1 — Your MCP URL</div>
    <input class="key-input" id="apiKey" type="text"
           placeholder="Paste your API key here…" oninput="updateUrl()" autocomplete="off">
    <div class="url-row">
      <div class="url-box" id="mcpUrl">https://<span id="host-display">…</span>/mcp?api_key=<span class="placeholder">YOUR_KEY</span></div>
      <button class="copy-btn" id="copyBtn" onclick="copyUrl()">Copy</button>
    </div>
    <p class="hint">Keep this URL private — it grants access to your analyst instance.</p>
  </div>

  <!-- ── Step 2: Platform ── -->
  <div class="card">
    <div class="card-label">Step 2 — Connect to Claude</div>
    <div class="tab-bar">
      <div class="tab active" onclick="switchTab('web')">🌐 Claude.ai</div>
      <div class="tab" onclick="switchTab('desktop')">🖥 Desktop</div>
      <div class="tab" onclick="switchTab('cli')">⌨ CLI</div>
    </div>

    <div class="tab-panel active" id="tab-web">
      <div class="step">
        <div class="step-num">1</div>
        <div class="step-body">Open <strong>claude.ai</strong> → <strong>Settings → Connectors → Customize</strong></div>
      </div>
      <div class="step">
        <div class="step-num">2</div>
        <div class="step-body">Click <strong>Add Custom Connector</strong> and set the name to <code>Orbis Quant Agents</code></div>
      </div>
      <div class="step">
        <div class="step-num">3</div>
        <div class="step-body">Paste your MCP URL from above and click <strong>Connect</strong></div>
      </div>
      <div class="step">
        <div class="step-num">4</div>
        <div class="step-body">Tools appear automatically in your next conversation — look for the <strong>⚙ toolbar icon</strong></div>
      </div>
    </div>

    <div class="tab-panel" id="tab-desktop">
      <div class="step">
        <div class="step-num">1</div>
        <div class="step-body">Open <code>~/Library/Application Support/Claude/claude_desktop_config.json</code></div>
      </div>
      <div class="step">
        <div class="step-num">2</div>
        <div class="step-body">Add this block inside <code>"mcpServers"</code>:
          <div class="snippet" id="desktopSnippet">
<span class="p">"orbis-quant"</span>: {<br>
&nbsp;&nbsp;<span class="p">"command"</span>: <span class="s">"npx"</span>,<br>
&nbsp;&nbsp;<span class="p">"args"</span>: [<span class="s">"-y"</span>, <span class="s">"mcp-remote@latest"</span>,<br>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<span class="s" id="desktopUrl">"https://…/mcp?api_key=YOUR_KEY"</span>]<br>
}
          </div>
        </div>
      </div>
      <div class="step">
        <div class="step-num">3</div>
        <div class="step-body">Save the file and <strong>restart Claude Desktop</strong></div>
      </div>
    </div>

    <div class="tab-panel" id="tab-cli">
      <div class="step">
        <div class="step-num">1</div>
        <div class="step-body">Run in your terminal:
          <div class="snippet" id="cliSnippet">
<span class="k">claude</span> mcp add orbis-quant \<br>
&nbsp;&nbsp;<span class="k">--transport</span> http \<br>
&nbsp;&nbsp;<span class="s" id="cliUrl">https://…/mcp?api_key=YOUR_KEY</span>
          </div>
        </div>
      </div>
      <div class="step">
        <div class="step-num">2</div>
        <div class="step-body">Verify with <code>claude mcp list</code> — you should see <strong>orbis-quant</strong></div>
      </div>
    </div>
  </div>

  <!-- ── Step 3: Try it ── -->
  <div class="card">
    <div class="card-label">Step 3 — Try these prompts</div>
    <div class="prompt-grid">
      <div class="prompt" onclick="copyPrompt(this)">Analyze RELIANCE.NS — give me the full Orbis Quant intelligence report</div>
      <div class="prompt" onclick="copyPrompt(this)">Pre-market setup for TCS and INFY — what are the key levels today?</div>
      <div class="prompt" onclick="copyPrompt(this)">Screen my watchlist: RELIANCE, HDFC, ICICIBANK, SBIN, WIPRO</div>
      <div class="prompt" onclick="copyPrompt(this)">Is HDFCBANK a buy right now? Run the full bull vs bear debate</div>
    </div>
  </div>

  <footer class="footer">
    <span>Orbis Quant Agents</span>
    <span class="footer-sep">·</span>
    <span>AI-powered · Indian markets</span>
    <span class="footer-sep">·</span>
    <a href="/health">Status</a>
  </footer>

</div>
<script>
const HOST = location.host;
document.getElementById('host-display').textContent = HOST;

function updateUrl() {
  const key = document.getElementById('apiKey').value.trim();
  const base = 'https://' + HOST + '/mcp';
  const plain = base + '?api_key=' + (key || 'YOUR_KEY');

  const box = document.getElementById('mcpUrl');
  if (key) {
    box.textContent = plain;
  } else {
    box.innerHTML = 'https://' + HOST + '/mcp?api_key=<span class="placeholder">YOUR_KEY</span>';
  }

  document.getElementById('desktopUrl').textContent = '"' + plain + '"';
  document.getElementById('cliUrl').textContent = plain;
}

function copyUrl() {
  const key = document.getElementById('apiKey').value.trim();
  const url = 'https://' + HOST + '/mcp' + (key ? '?api_key=' + encodeURIComponent(key) : '');
  navigator.clipboard.writeText(url).then(() => {
    const btn = document.getElementById('copyBtn');
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 2000);
  });
}

function copyPrompt(el) {
  navigator.clipboard.writeText(el.textContent.trim()).then(() => {
    const orig = el.textContent;
    el.textContent = 'Copied to clipboard!';
    setTimeout(() => { el.textContent = orig; }, 1500);
  });
}

function switchTab(name) {
  const names = ['web', 'desktop', 'cli'];
  document.querySelectorAll('.tab').forEach((t, i) => t.classList.toggle('active', names[i] === name));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === 'tab-' + name));
}

updateUrl();
</script>
</body>
</html>"""


@mcp.custom_route("/connect", methods=["GET"])
async def connect_page(_request: Request) -> HTMLResponse:
    """Human-readable setup page — share this URL with anyone you want to onboard."""
    return HTMLResponse(_CONNECT_HTML)


# Lazy-init the graph so import doesn't block server startup
# Keyed by (analyst_tuple, provider) so primary and fallback graphs are cached separately.
_graph_instances = {}

def _get_graph(analysts=None, provider_override: str | None = None):
    global _graph_instances
    analyst_list = analysts or ["market", "social", "news", "fundamentals"]
    analyst_tuple = tuple(sorted(analyst_list))

    provider = provider_override or os.getenv("LLM_PROVIDER", "openai")
    cache_key = (analyst_tuple, provider)

    if cache_key not in _graph_instances:
        from orbisquantagents.graph.orbis_quant_graph import OrbisQuantAgentsGraph
        from orbisquantagents.default_config import DEFAULT_CONFIG

        cfg = DEFAULT_CONFIG.copy()
        cfg["max_debate_rounds"] = 1

        if provider_override:
            cfg["llm_provider"]    = provider_override
            cfg["deep_think_llm"]  = os.getenv("FALLBACK_DEEP_THINK_LLM",  cfg["deep_think_llm"])
            cfg["quick_think_llm"] = os.getenv("FALLBACK_QUICK_THINK_LLM", cfg["quick_think_llm"])
            # Allow a custom base URL for the fallback (required for remote Ollama).
            # factory.py will default Ollama to OLLAMA_BASE_URL / localhost if this is unset.
            fallback_base_url = os.getenv("FALLBACK_BASE_URL")
            if fallback_base_url:
                cfg["backend_url"] = fallback_base_url
            elif provider_override != "openai":
                cfg["backend_url"] = None  # let factory.py apply provider-specific defaults
        else:
            cfg["llm_provider"]    = os.getenv("LLM_PROVIDER",    cfg["llm_provider"])
            cfg["deep_think_llm"]  = os.getenv("DEEP_THINK_LLM",  cfg["deep_think_llm"])
            cfg["quick_think_llm"] = os.getenv("QUICK_THINK_LLM", cfg["quick_think_llm"])
            primary_base_url = os.getenv("BACKEND_URL")
            if primary_base_url:
                cfg["backend_url"] = primary_base_url
            elif cfg["llm_provider"] != "openai":
                cfg["backend_url"] = None

        _graph_instances[cache_key] = OrbisQuantAgentsGraph(
            selected_analysts=analyst_list,
            debug=False,
            config=cfg,
        )
    return _graph_instances[cache_key]


def _is_provider_limit_error(exc: Exception) -> bool:
    """Return True if the error should trigger a fallback retry on a different provider.

    Covers: quota exhaustion, rate limits, overload, AND timeouts — because a
    slow local Ollama instance timing out on the first provider should still
    fall back to a fast cloud provider rather than returning an empty error.
    """
    s = str(exc).lower()
    return any(x in s for x in (
        "503", "429", "resource_exhausted", "overloaded",
        "rate limit", "quota", "too many requests",
        "timed out", "timeout", "apitimeouterror",
        "connection error", "connection refused", "remotedisconnected",
    ))


# ── Report profiles ───────────────────────────────────────────────────────────
# Maps a user-facing intent label to the analyst subset and debate depth.
# Kept in sync with web_ui.py's _REPORT_PROFILES.

_REPORT_PROFILES: dict[str, dict] = {
    "pre_market": {
        "analysts": ["market"],
        "max_debate_rounds": 1,
        "label": "Pre-market setup",
        "desc": "Price levels, RSI, MACD — fast check before the open",
    },
    "swing_trade": {
        "analysts": ["market", "news"],
        "max_debate_rounds": 1,
        "label": "Swing trade entry",
        "desc": "Technical setup + news catalyst for 1–5 day trades",
    },
    "long_term": {
        "analysts": ["fundamentals", "news"],
        "max_debate_rounds": 3,
        "label": "Long-term investing",
        "desc": "PE, revenue, promoter holding, debt — worth holding?",
    },
    "sentiment": {
        "analysts": ["social", "news"],
        "max_debate_rounds": 1,
        "label": "Sentiment & news",
        "desc": "Social tone, headlines, SEBI filings, FII/DII flows",
    },
    "full": {
        "analysts": ["market", "social", "news", "fundamentals"],
        "max_debate_rounds": 3,
        "label": "Full intelligence",
        "desc": "All analysts + bull vs bear debate + PM verdict",
    },
}


# ── Tools ─────────────────────────────────────────────────────────────────────

def _run_pipeline(symbol: str, trade_date: str, analyst_list: list[str],
                  provider_override: str | None = None) -> dict:
    """Synchronous helper — runs the blocking graph pipeline."""
    graph = _get_graph(analyst_list, provider_override=provider_override)
    final_state, decision = graph.propagate(symbol, trade_date)
    result = {
        "symbol":     symbol,
        "trade_date": trade_date,
        "analysts":   analyst_list,
        "decision":   decision,
        "status":     "success",
    }
    # Attach analyst reports if the graph produced them
    for key in ("market_report", "fundamentals_report", "sentiment_report",
                "news_report", "small_cap_report", "investment_plan",
                "final_trade_decision"):
        val = final_state.get(key)
        if val:
            result[key] = val
    # Attach debate summary (judge decisions only — histories can be huge)
    debate = final_state.get("investment_debate_state", {})
    if debate:
        result["debate_summary"] = {
            "judge_decision": debate.get("judge_decision", ""),
            "bull_rounds":    len(debate.get("bull_history", [])),
            "bear_rounds":    len(debate.get("bear_history", [])),
        }
    return result


def _fmt(text: str | None, fallback: str = "") -> str:
    """Return text stripped, or fallback if empty."""
    return (text or "").strip() or fallback


def _format_analysis_report(result: dict) -> str:
    """
    Convert the raw pipeline result dict into a readable markdown report
    so Claude can present it conversationally rather than as raw JSON.
    """
    symbol = result.get("symbol", "?")
    trade_date = result.get("trade_date", "?")
    analysts_used = result.get("analysts", [])
    decision = result.get("decision", "UNKNOWN")
    if isinstance(decision, dict):
        verdict   = decision.get("decision", "UNKNOWN")
        confidence = decision.get("confidence")
        reason    = decision.get("reason", "")
    else:
        verdict    = str(decision)
        confidence = None
        reason     = ""

    provider = result.get("provider_used", os.getenv("LLM_PROVIDER", "?"))
    model    = os.getenv("DEEP_THINK_LLM", "?")

    _VERDICT_EMOJI = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}
    emoji = _VERDICT_EMOJI.get(verdict.upper(), "⚪")

    lines = [
        f"# Orbis Quant Intelligence — {symbol}",
        f"*{trade_date}  ·  {', '.join(a.title() for a in analysts_used)} analysts  ·  {model} via {provider}*",
        "",
    ]

    # Per-analyst reports
    _SECTION = {
        "market_report":       ("📊", "Technical Analysis"),
        "fundamentals_report": ("📈", "Fundamental Analysis"),
        "news_report":         ("📰", "News Analysis"),
        "sentiment_report":    ("💬", "Sentiment Analysis"),
        "small_cap_report":    ("🏷️", "Small Cap / PSU Analysis"),
    }
    for key, (icon, title) in _SECTION.items():
        body = _fmt(result.get(key))
        if body:
            lines += [f"## {icon} {title}", "", body, ""]

    # Debate summary
    debate = result.get("debate_summary", {})
    judge  = _fmt(debate.get("judge_decision")) if debate else ""
    if judge:
        lines += ["## 🥊 Bull vs Bear Debate", ""]
        lines += [f"**Judge's decision:**", "", judge, ""]

    # Investment plan
    plan = _fmt(result.get("investment_plan"))
    if plan:
        lines += ["## 📋 Investment Plan", "", plan, ""]

    # Final trade decision (raw signal text if available)
    raw_signal = _fmt(result.get("final_trade_decision"))
    if raw_signal and raw_signal != verdict:
        lines += ["## 🤖 Portfolio Manager Signal", "", raw_signal, ""]

    # Verdict banner — always last
    conf_str = f"  ·  Confidence: **{confidence}%**" if confidence else ""
    lines += [
        "---",
        f"## {emoji} Final Verdict: **{verdict}**{conf_str}",
    ]
    if reason:
        lines += ["", f"*{reason}*"]

    return "\n".join(lines)


def _get_price_snapshot_sync(symbol: str) -> str:
    """Synchronous yfinance snapshot with RSI + MACD — called via asyncio.to_thread."""
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        info = t.info or {}
        hist = t.history(period="6mo")

        price      = info.get("currentPrice") or info.get("regularMarketPrice")
        prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
        day_high   = info.get("dayHigh") or info.get("regularMarketDayHigh")
        day_low    = info.get("dayLow") or info.get("regularMarketDayLow")
        volume     = info.get("volume") or info.get("regularMarketVolume")
        avg_vol    = info.get("averageVolume")
        week52_hi  = info.get("fiftyTwoWeekHigh")
        week52_lo  = info.get("fiftyTwoWeekLow")
        mktcap     = info.get("marketCap")
        pe         = info.get("trailingPE") or info.get("forwardPE")
        eps        = info.get("trailingEps")
        book_val   = info.get("bookValue")
        name       = info.get("longName") or info.get("shortName") or symbol

        def fmt_price(v):
            return f"₹{v:,.2f}" if v else "N/A"

        def fmt_mktcap(v):
            if v is None: return "N/A"
            if v >= 1e12: return f"₹{v/1e12:.2f}L Cr"
            if v >= 1e9:  return f"₹{v/1e9:.1f}K Cr"
            if v >= 1e7:  return f"₹{v/1e7:.1f} Cr"
            return f"₹{v:,.0f}"

        def fmt_vol(v):
            if v is None: return "N/A"
            if v >= 1e7:  return f"{v/1e7:.1f}Cr shares"
            if v >= 1e5:  return f"{v/1e5:.1f}L shares"
            return f"{v:,} shares"

        chg = ""
        if price and prev_close:
            pct = (price - prev_close) / prev_close * 100
            arrow = "▲" if pct >= 0 else "▼"
            chg = f" ({arrow}{abs(pct):.2f}% today)"

        vol_note = ""
        if volume and avg_vol:
            ratio = volume / avg_vol
            if ratio > 1.5:
                vol_note = f" — ⚠️ {ratio:.1f}× avg (unusual activity)"
            elif ratio < 0.5:
                vol_note = f" — 📉 {ratio:.1f}× avg (quiet)"

        # ── RSI(14) ────────────────────────────────────────────────────────────
        rsi_str = "N/A"
        rsi_note = ""
        if hist is not None and len(hist) >= 15:
            delta = hist["Close"].diff()
            gain = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
            loss = (-delta.clip(upper=0)).ewm(com=13, adjust=False).mean()
            rs = gain / loss.replace(0, float("nan"))
            rsi_val = (100 - 100 / (1 + rs)).iloc[-1]
            rsi_str = f"{rsi_val:.1f}"
            if rsi_val >= 70:   rsi_note = "🔴 Overbought"
            elif rsi_val <= 30: rsi_note = "🟢 Oversold — potential bounce"
            elif rsi_val >= 55: rsi_note = "📈 Bullish momentum"
            else:               rsi_note = "📉 Weak / bearish momentum"

        # ── MACD(12,26,9) ──────────────────────────────────────────────────────
        macd_str = "N/A"
        if hist is not None and len(hist) >= 27:
            ema12  = hist["Close"].ewm(span=12, adjust=False).mean()
            ema26  = hist["Close"].ewm(span=26, adjust=False).mean()
            macd   = ema12 - ema26
            signal = macd.ewm(span=9, adjust=False).mean()
            m, s   = macd.iloc[-1], signal.iloc[-1]
            prev_m, prev_s = macd.iloc[-2], signal.iloc[-2]
            cross = ""
            if prev_m < prev_s and m >= s: cross = " 🟢 Bullish crossover!"
            elif prev_m > prev_s and m <= s: cross = " 🔴 Bearish crossover!"
            macd_str = f"{m:+.2f} / Signal {s:+.2f}{cross}"

        # ── SMA trend ─────────────────────────────────────────────────────────
        trend_str = ""
        if hist is not None and len(hist) >= 50 and price:
            sma50  = hist["Close"].rolling(50).mean().iloc[-1]
            above50 = price > sma50
            trend_str = f"Above 50 DMA (₹{sma50:.0f}) — bullish" if above50 \
                        else f"Below 50 DMA (₹{sma50:.0f}) — bearish"
            if len(hist) >= 200:
                sma200 = hist["Close"].rolling(200).mean().iloc[-1]
                above200 = price > sma200
                trend_str += f"  ·  {'Above' if above200 else 'Below'} 200 DMA (₹{sma200:.0f})"

        lines = [
            f"## {name} ({symbol}) — Live Snapshot",
            "",
            f"**Price:** {fmt_price(price)}{chg}",
            f"**Day Range:** {fmt_price(day_low)} – {fmt_price(day_high)}",
            f"**52-Week Range:** {fmt_price(week52_lo)} – {fmt_price(week52_hi)}",
            f"**Volume:** {fmt_vol(volume)}{vol_note}",
            f"**Market Cap:** {fmt_mktcap(mktcap)}",
            "",
            "**Quick Technicals** *(no AI — raw data)*",
            f"RSI(14): **{rsi_str}** — {rsi_note}",
            f"MACD: {macd_str}",
        ]
        if trend_str:
            lines.append(f"Trend: {trend_str}")
        lines += [
            "",
            "**Valuation**",
            f"PE: {f'{pe:.1f}x' if pe else 'N/A'}  ·  EPS: {fmt_price(eps)}  ·  Book Value: {fmt_price(book_val)}",
            "",
            "*Now calling AI technical analyst for deeper interpretation...*",
        ]
        return "\n".join(lines)

    except Exception as exc:
        return f"Could not fetch snapshot for {symbol}: {exc}"


_ANALYST_LABELS = {
    "market":       "Technical analyst",
    "fundamentals": "Fundamental analyst",
    "social":       "Sentiment analyst",
    "news":         "News analyst",
}

_ANALYST_STAGE_DESCS = {
    "market":       "Technical analyst — scanning price action, RSI, MACD, Camarilla pivot levels",
    "fundamentals": "Fundamental analyst — reviewing PE ratio, EPS growth, promoter holding, debt ratios",
    "social":       "Sentiment analyst — reading social tone, FII/DII flows, retail investor sentiment",
    "news":         "News analyst — scanning NSE filings, SEBI alerts, corporate announcements",
}


@mcp.tool()
async def get_price_snapshot(symbol: str) -> str:
    """
    STEP 1 — Always call this first. Instant live market data, no AI needed.

    Returns in ~2 seconds: current price + % change, day range, 52-week range,
    volume vs average (flags unusual activity), market cap, PE ratio, EPS,
    book value.

    After this returns, narrate what the numbers mean — is it near a 52-week
    high/low? Is volume unusually high (potential breakout or dump)?
    Is the PE cheap or expensive vs sector? Then proceed to get_technical_analysis.

    Args:
        symbol: NSE/BSE ticker (e.g. "RELIANCE", "TCS", "NIFTY"). .NS suffix added automatically.
    """
    if not symbol.endswith((".NS", ".BO")):
        symbol = symbol.upper() + ".NS"
    return await asyncio.to_thread(_get_price_snapshot_sync, symbol)


@mcp.tool()
async def analyze_stock(
    symbol: str,
    trade_date: Optional[str] = None,
    analysts: Optional[str] = "market,social,news,fundamentals",
    ctx: Context = None,
) -> str:
    """
    ALL-IN-ONE pipeline — runs all analysts + debate + PM verdict in one call.

    PREFER the staged flow (get_price_snapshot → get_technical_analysis →
    get_fundamental_analysis → get_sentiment_analysis → debate_trade) because
    it lets you narrate after each step. Use this tool only when the user
    explicitly asks for a "full analysis in one go" or "quick summary."

    Runs 7 agents in sequence (takes 2–15 min depending on the LLM provider):
      1. Technical analyst  — price action, Camarilla levels, RSI, MACD
      2. Fundamental analyst — PE, EPS, revenue, promoter holding, debt
      3. Sentiment analyst  — social tone, FII/DII flows
      4. News analyst       — recent filings, SEBI alerts, headlines
      5. Bull researcher    — builds the bullish thesis
      6. Bear researcher    — builds the counter-case
      7. Portfolio Manager  — weighs both sides, issues BUY / SELL / HOLD

    Returns a full markdown report with all analyst findings and the verdict.

    Args:
        symbol:     NSE/BSE ticker (e.g. "RELIANCE.NS", "INFY.NS"). Append .NS for NSE.
        trade_date: Analysis date as YYYY-MM-DD. Defaults to today.
        analysts:   Comma-separated subset: market, social, news, fundamentals.
    """
    if not symbol.endswith((".NS", ".BO")):
        symbol = symbol.upper() + ".NS"

    if trade_date is None:
        trade_date = date.today().strftime("%Y-%m-%d")

    analyst_list = [a.strip() for a in analysts.split(",")]

    primary_provider = os.getenv("LLM_PROVIDER", "openai")
    fallback_provider = os.getenv("FALLBACK_LLM_PROVIDER")
    model = os.getenv("DEEP_THINK_LLM", "unknown")
    team_str = "  ·  ".join(_ANALYST_LABELS.get(a, a.title()) for a in analyst_list)
    n_agents = len(analyst_list) + 3  # analysts + bull + bear + PM

    # Build per-stage progress messages
    stages = [_ANALYST_STAGE_DESCS[a] for a in analyst_list if a in _ANALYST_STAGE_DESCS]
    stages += [
        "Bull researcher — building the bullish thesis with supporting evidence",
        "Bear researcher — identifying risks and counter-arguments",
        "Portfolio Manager — weighing evidence, issuing final BUY / SELL / HOLD verdict",
    ]

    async def emit(msg: str):
        if ctx:
            try:
                await ctx.info(msg)
            except Exception:
                pass
        else:
            logger.info(msg)

    # Opening banner
    await emit(f"Orbis Quant Intelligence — {symbol}")
    await emit(f"Date: {trade_date}  |  {n_agents} agents  |  {model} via {primary_provider}")
    await emit(f"Analyst team: {team_str}")
    await emit("Pipeline started — each agent runs in sequence, building on the previous")

    # Background updater sends one stage message every ~35 s while the thread runs.
    # Uses a simple 1-second sleep loop so task cancellation is always clean —
    # no asyncio.wait_for whose exception type changed in Python 3.12.
    cancelled = False

    async def _stage_updater():
        for i, stage in enumerate(stages, 1):
            if cancelled:
                return
            await emit(f"[{i}/{len(stages)}] {stage}…")
            for _ in range(35):
                if cancelled:
                    return
                await asyncio.sleep(1)

    updater_task = asyncio.create_task(_stage_updater())

    async def _finish_updater():
        nonlocal cancelled
        cancelled = True
        updater_task.cancel()
        try:
            await updater_task
        except (asyncio.CancelledError, Exception):
            pass

    try:
        result = await asyncio.to_thread(_run_pipeline, symbol, trade_date, analyst_list)
        await _finish_updater()

        decision = result.get("decision", "UNKNOWN")
        if isinstance(decision, dict):
            verdict = decision.get("decision", "UNKNOWN")
            confidence = decision.get("confidence")
            conf_str = f"  (confidence: {confidence}%)" if confidence else ""
            await emit(f"Analysis complete — Verdict: {verdict}{conf_str}")
        else:
            await emit(f"Analysis complete — Verdict: {decision}")

        return _format_analysis_report(result)

    except Exception as primary_exc:
        await _finish_updater()

        if fallback_provider and fallback_provider != primary_provider and _is_provider_limit_error(primary_exc):
            logger.warning(
                "Primary provider %s failed for %s (%s) — retrying with fallback %s",
                primary_provider, symbol, type(primary_exc).__name__, fallback_provider,
            )
            await emit(
                f"Primary provider ({primary_provider}) returned a quota/overload error — "
                f"switching to fallback ({fallback_provider}) and retrying…"
            )
            try:
                result = await asyncio.to_thread(
                    _run_pipeline, symbol, trade_date, analyst_list, fallback_provider
                )
                result["provider_used"] = fallback_provider
                result["primary_error"] = str(primary_exc)[:200]

                decision = result.get("decision", "UNKNOWN")
                verdict = decision.get("decision", decision) if isinstance(decision, dict) else decision
                await emit(f"Fallback analysis complete — Verdict: {verdict}")
                return _format_analysis_report(result)

            except Exception as fallback_exc:
                logger.exception("Fallback provider %s also failed for %s", fallback_provider, symbol)
                await emit(f"Fallback provider ({fallback_provider}) also failed — returning error details")
                return json.dumps({
                    "symbol":           symbol,
                    "status":           "error",
                    "message":          str(fallback_exc),
                    "primary_error":    str(primary_exc)[:200],
                    "provider":         fallback_provider,
                    "primary_provider": primary_provider,
                    "hint": (
                        f"Both {primary_provider.upper()} and {fallback_provider.upper()} failed. "
                        "Check API keys and quota."
                    ),
                })

        logger.exception("analyze_stock failed for %s", symbol)
        await emit(f"Analysis failed — {type(primary_exc).__name__}: {str(primary_exc)[:120]}")
        return json.dumps({
            "symbol":   symbol,
            "status":   "error",
            "message":  str(primary_exc),
            "provider": primary_provider,
            "model":    model,
            "hint":     (
                f"Check that the {primary_provider.upper()} API key is set and valid. "
                f"Current provider={primary_provider}, model={model}. "
                + ("Set FALLBACK_LLM_PROVIDER env var to enable automatic failover."
                   if not fallback_provider else "")
            ),
        })


@mcp.tool()
async def get_technical_analysis(symbol: str) -> str:
    """
    STEP 2 — AI technical analyst. Call after get_price_snapshot.

    Runs the technical analyst agent. Returns Camarilla pivot levels, trend
    direction (above/below 50/200 DMA), RSI with overbought/oversold signal,
    MACD crossover status, key support and resistance zones.

    After this returns, explain the chart setup in plain English:
    Is the stock in an uptrend or downtrend? Is RSI showing momentum or
    exhaustion? What are the key levels to watch? Then offer to go deeper
    with get_fundamental_analysis or get_sentiment_analysis.

    Args:
        symbol: NSE ticker (e.g. "RELIANCE", "TCS"). .NS suffix added automatically.
    """
    return await analyze_stock(symbol=symbol, analysts="market")


@mcp.tool()
async def get_fundamental_analysis(symbol: str) -> str:
    """
    STEP 3 — AI fundamental analyst. Call after get_technical_analysis.

    Returns PE ratio vs sector average, EPS trend (growing/shrinking),
    revenue and profit growth YoY, promoter holding % and direction,
    FII/DII ownership trends, debt-to-equity ratio, and valuation verdict.

    After this returns, give an opinion: Is the stock cheap or expensive
    relative to its growth? Is promoter holding declining (red flag)?
    Is debt manageable? Then move to get_sentiment_analysis.

    Args:
        symbol: NSE ticker (e.g. "HDFCBANK", "WIPRO"). .NS suffix added automatically.
    """
    return await analyze_stock(symbol=symbol, analysts="fundamentals")


@mcp.tool()
async def get_sentiment_analysis(symbol: str) -> str:
    """
    STEP 4 — AI news and sentiment analyst. Call after get_fundamental_analysis.

    Returns recent news sentiment score, key headlines from the last 7 days,
    SEBI filings and corporate announcements, FII/DII net flow direction,
    and social media retail sentiment tone.

    After this returns, highlight the single most important news item or
    sentiment signal. Is there a catalyst (earnings, acquisition, SEBI order)?
    Is smart money (FII/DII) accumulating or distributing? Then move to debate_trade.

    Args:
        symbol: NSE ticker. .NS suffix added automatically.
    """
    return await analyze_stock(symbol=symbol, analysts="social,news")


@mcp.tool()
async def debate_trade(symbol: str, trade_date: Optional[str] = None) -> str:
    """
    STEP 5 — Final step. Bull vs bear debate + Portfolio Manager verdict.

    Runs all four analyst agents, then:
    - Bull researcher builds the best-case thesis with evidence
    - Bear researcher challenges it with risks and counter-arguments
    - Portfolio Manager weighs both sides and issues BUY / SELL / HOLD
      with a confidence score and suggested entry/stop/target levels

    After this returns, present the final verdict clearly and give your own
    view on whether the bull or bear case is stronger based on all the data.

    Args:
        symbol:     NSE ticker. .NS suffix added automatically.
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


@mcp.tool()
async def request_analysis(
    symbol: str,
    report_type: str,
    trade_date: Optional[str] = None,
) -> str:
    """
    Run analysis on a stock using a named report profile.

    Use this instead of analyze_stock when the user specifies what they're
    looking for — it picks the right analyst team and debate depth automatically.

    report_type options (choose the closest match to the user's intent):
      "pre_market"  — price levels, RSI, MACD. Fast check before the open.
      "swing_trade" — technical setup + news catalyst for 1–5 day trades.
      "long_term"   — PE, revenue, promoter holding — worth holding long?
      "sentiment"   — social tone, headlines, SEBI filings, FII/DII flows.
      "full"        — all analysts + bull vs bear debate + PM verdict (default).

    Args:
        symbol:      NSE/BSE ticker (e.g. "RELIANCE.NS", "INFY.NS").
        report_type: One of the profile keys listed above.
        trade_date:  Analysis date as YYYY-MM-DD. Defaults to today.

    Returns:
        JSON string with analysis and the profile label that was used.
    """
    profile = _REPORT_PROFILES.get(report_type.lower())
    if profile is None:
        available = ", ".join(f'"{k}"' for k in _REPORT_PROFILES)
        return json.dumps({
            "status": "error",
            "message": f"Unknown report_type '{report_type}'. Available: {available}",
        })

    analysts_str = ",".join(profile["analysts"])
    result_raw = await analyze_stock(symbol=symbol, trade_date=trade_date, analysts=analysts_str)

    try:
        result = json.loads(result_raw)
    except Exception:
        return result_raw

    result["report_type"] = report_type
    result["report_label"] = profile["label"]
    result["report_desc"] = profile["desc"]
    return json.dumps(result, indent=2, default=str)


@mcp.resource("reports://profiles")
def list_report_profiles() -> str:
    """Lists all named report profiles and what each one analyses."""
    return json.dumps(
        {k: {"label": v["label"], "analysts": v["analysts"], "desc": v["desc"]}
         for k, v in _REPORT_PROFILES.items()},
        indent=2,
    )


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
