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
from starlette.responses import JSONResponse, HTMLResponse
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


_CONNECT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Connect — Orbis Quant Agents</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
       background:#0a0f1e;color:#e2e8f0;min-height:100vh;padding:40px 20px}
  .wrap{max-width:680px;margin:0 auto}
  .logo{display:flex;align-items:center;gap:12px;margin-bottom:48px}
  .logo-icon{width:40px;height:40px;background:linear-gradient(135deg,#6366f1,#8b5cf6);
             border-radius:10px;display:flex;align-items:center;justify-content:center;
             font-size:20px}
  .logo-name{font-size:18px;font-weight:700;letter-spacing:-0.3px}
  .logo-tag{font-size:11px;color:#6366f1;font-weight:600;letter-spacing:0.05em;
            text-transform:uppercase;margin-top:1px}
  h1{font-size:28px;font-weight:700;line-height:1.2;letter-spacing:-0.5px;margin-bottom:8px}
  .subtitle{color:#94a3b8;font-size:15px;margin-bottom:40px;line-height:1.5}
  .card{background:#111827;border:1px solid #1f2937;border-radius:14px;
        padding:28px;margin-bottom:20px}
  .card-title{font-size:13px;font-weight:600;color:#6366f1;letter-spacing:0.06em;
              text-transform:uppercase;margin-bottom:20px;display:flex;
              align-items:center;gap:8px}
  .step{display:flex;gap:16px;margin-bottom:18px;align-items:flex-start}
  .step:last-child{margin-bottom:0}
  .step-num{min-width:26px;height:26px;background:#1e1b4b;border:1px solid #4338ca;
            border-radius:50%;display:flex;align-items:center;justify-content:center;
            font-size:12px;font-weight:700;color:#818cf8;flex-shrink:0;margin-top:1px}
  .step-text{font-size:14px;color:#cbd5e1;line-height:1.55}
  .step-text strong{color:#e2e8f0;font-weight:600}
  .step-text code{background:#1f2937;border:1px solid #374151;border-radius:5px;
                  padding:1px 6px;font-size:13px;color:#a5b4fc;font-family:monospace}
  .key-row{display:flex;gap:10px;margin:20px 0 6px}
  .key-input{flex:1;background:#0f172a;border:1px solid #374151;border-radius:8px;
             padding:10px 14px;color:#e2e8f0;font-size:14px;font-family:monospace;
             outline:none;transition:border-color .2s}
  .key-input:focus{border-color:#6366f1}
  .key-input::placeholder{color:#4b5563}
  .url-box{background:#0f172a;border:1px solid #374151;border-radius:8px;
           padding:14px;position:relative;margin-bottom:6px}
  .url-text{font-family:monospace;font-size:13px;color:#a5b4fc;word-break:break-all;
            line-height:1.5;padding-right:70px}
  .copy-btn{position:absolute;top:10px;right:10px;background:#4338ca;border:none;
            color:#e0e7ff;font-size:12px;font-weight:600;padding:5px 12px;
            border-radius:6px;cursor:pointer;transition:background .15s}
  .copy-btn:hover{background:#4f46e5}
  .copy-btn.copied{background:#065f46;color:#6ee7b7}
  .hint{font-size:12px;color:#4b5563;margin-bottom:0}
  .prompt-box{background:#0f172a;border:1px solid #1f2937;border-radius:8px;
              padding:14px 16px;font-size:14px;color:#94a3b8;line-height:1.5;
              font-style:italic;position:relative;margin-top:12px}
  .prompt-box::before{content:'"';font-size:20px;color:#4338ca;
                       position:absolute;top:8px;left:10px;font-style:normal}
  .prompt-text{padding-left:16px}
  .tabs{display:flex;gap:4px;margin-bottom:20px}
  .tab{padding:7px 16px;border-radius:7px;font-size:13px;font-weight:500;
       cursor:pointer;border:1px solid transparent;color:#64748b;transition:all .15s}
  .tab.active{background:#1e1b4b;border-color:#4338ca;color:#a5b4fc}
  .tab:hover:not(.active){color:#94a3b8}
  .tab-panel{display:none}
  .tab-panel.active{display:block}
  .footer{text-align:center;margin-top:48px;color:#374151;font-size:13px}
  .badge{display:inline-block;background:#1e1b4b;border:1px solid #312e81;
         color:#818cf8;font-size:11px;font-weight:600;padding:3px 8px;
         border-radius:20px;letter-spacing:0.04em;text-transform:uppercase;margin-left:8px}
  .platform-icon{font-size:15px}
</style>
</head>
<body>
<div class="wrap">

  <div class="logo">
    <div class="logo-icon">⚡</div>
    <div>
      <div class="logo-name">Orbis Quant Agents</div>
      <div class="logo-tag">NSE · BSE · AI-Powered</div>
    </div>
  </div>

  <h1>Connect to your AI trading analyst</h1>
  <p class="subtitle">Multi-agent analysis for Indian markets — technical, fundamental, sentiment &amp; debate.<br>
  Works inside Claude.ai, Claude Desktop, and the Claude CLI.</p>

  <!-- Step 0: Enter API key -->
  <div class="card">
    <div class="card-title">🔑 Your MCP URL</div>
    <div class="step-text" style="margin-bottom:14px;color:#94a3b8;font-size:14px">
      Enter the API key you received, then copy the personalised URL below.
    </div>
    <div class="key-row">
      <input class="key-input" id="apiKey" type="text" placeholder="Paste your API key here…"
             oninput="updateUrl()">
    </div>
    <div class="url-box">
      <div class="url-text" id="mcpUrl">https://RAILWAY_HOST/mcp?api_key=<span style="color:#f59e0b">YOUR_KEY</span></div>
      <button class="copy-btn" id="copyBtn" onclick="copyUrl()">Copy</button>
    </div>
    <p class="hint">Share your key only with people you trust — it grants access to your Ollama instance.</p>
  </div>

  <!-- Platform tabs -->
  <div class="card">
    <div class="card-title">📡 Connection steps</div>
    <div class="tabs">
      <div class="tab active platform-icon" onclick="switchTab('web')">🌐 Claude.ai</div>
      <div class="tab platform-icon" onclick="switchTab('desktop')">🖥 Desktop</div>
      <div class="tab platform-icon" onclick="switchTab('cli')">⌨ CLI</div>
    </div>

    <div class="tab-panel active" id="tab-web">
      <div class="step"><div class="step-num">1</div><div class="step-text">
        Open <strong>claude.ai</strong> and go to <strong>Settings → Connectors → Customize</strong></div></div>
      <div class="step"><div class="step-num">2</div><div class="step-text">
        Click the <code>+</code> icon next to the search bar, then <strong>Add Custom Connector</strong></div></div>
      <div class="step"><div class="step-num">3</div><div class="step-text">
        Set the name to <code>Orbis Quant Agents</code> and paste your MCP URL from above</div></div>
      <div class="step"><div class="step-num">4</div><div class="step-text">
        Click <strong>Connect</strong> — tools will appear in your next conversation</div></div>
    </div>

    <div class="tab-panel" id="tab-desktop">
      <div class="step"><div class="step-num">1</div><div class="step-text">
        Open <strong>~/Library/Application Support/Claude/claude_desktop_config.json</strong></div></div>
      <div class="step"><div class="step-num">2</div><div class="step-text">
        Add the block below inside <code>"mcpServers"</code>:
        <div class="url-box" style="margin-top:10px;padding-right:14px">
          <div class="url-text" style="font-size:12px;padding-right:0" id="desktopSnippet">
            "orbis-quant": {<br>
            &nbsp;&nbsp;"command": "npx",<br>
            &nbsp;&nbsp;"args": ["-y","mcp-remote@latest",<br>
            &nbsp;&nbsp;&nbsp;&nbsp;"https://RAILWAY_HOST/mcp?api_key=YOUR_KEY"]<br>
            }
          </div>
        </div>
      </div></div>
      <div class="step"><div class="step-num">3</div><div class="step-text">
        Save the file and <strong>restart Claude Desktop</strong></div></div>
    </div>

    <div class="tab-panel" id="tab-cli">
      <div class="step"><div class="step-num">1</div><div class="step-text">
        Run in your terminal:
        <div class="url-box" style="margin-top:10px;padding-right:14px">
          <div class="url-text" style="padding-right:0" id="cliSnippet">
            claude mcp add orbis-quant \\<br>
            &nbsp;&nbsp;--transport http \\<br>
            &nbsp;&nbsp;https://RAILWAY_HOST/mcp?api_key=YOUR_KEY
          </div>
        </div>
      </div></div>
      <div class="step"><div class="step-num">2</div><div class="step-text">
        Verify with <code>claude mcp list</code> — you should see <strong>orbis-quant</strong></div></div>
    </div>
  </div>

  <!-- Test prompts -->
  <div class="card">
    <div class="card-title">🧪 Test your connection</div>
    <div class="step-text" style="margin-bottom:4px;color:#94a3b8">
      Once connected, try one of these prompts in Claude:
    </div>
    <div class="prompt-box"><div class="prompt-text">
      Analyze RELIANCE.NS using Orbis Quant — give me the full intelligence report
    </div></div>
    <div class="prompt-box" style="margin-top:8px"><div class="prompt-text">
      Give me a pre-market setup for TCS and INFY
    </div></div>
    <div class="prompt-box" style="margin-top:8px"><div class="prompt-text">
      Screen my watchlist: RELIANCE, HDFC, ICICIBANK, SBIN, WIPRO
    </div></div>
  </div>

  <div class="footer">
    Orbis Quant Agents &nbsp;·&nbsp; Powered by <strong>qwen3</strong> via Ollama &nbsp;·&nbsp;
    <span style="color:#4b5563">Free · Private · Local AI</span>
  </div>

</div>
<script>
const HOST = location.host;

function updateUrl() {
  const key = document.getElementById('apiKey').value.trim();
  const base = 'https://' + HOST + '/mcp';
  const full = key ? base + '?api_key=' + encodeURIComponent(key) : base + '?api_key=<span style="color:#f59e0b">YOUR_KEY</span>';
  document.getElementById('mcpUrl').innerHTML = full;

  const plain = key ? base + '?api_key=' + key : base + '?api_key=YOUR_KEY';

  document.getElementById('desktopSnippet').innerHTML =
    '"orbis-quant": {<br>' +
    '&nbsp;&nbsp;"command": "npx",<br>' +
    '&nbsp;&nbsp;"args": ["-y","mcp-remote@latest",<br>' +
    '&nbsp;&nbsp;&nbsp;&nbsp;"' + plain + '"]<br>}';

  document.getElementById('cliSnippet').innerHTML =
    'claude mcp add orbis-quant \\\\<br>' +
    '&nbsp;&nbsp;--transport http \\\\<br>' +
    '&nbsp;&nbsp;' + plain;
}

function copyUrl() {
  const key = document.getElementById('apiKey').value.trim();
  const url = 'https://' + HOST + '/mcp' + (key ? '?api_key=' + key : '');
  navigator.clipboard.writeText(url).then(() => {
    const btn = document.getElementById('copyBtn');
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 2000);
  });
}

function switchTab(name) {
  document.querySelectorAll('.tab').forEach((t,i) => {
    const names = ['web','desktop','cli'];
    t.classList.toggle('active', names[i] === name);
  });
  document.querySelectorAll('.tab-panel').forEach(p => {
    p.classList.toggle('active', p.id === 'tab-' + name);
  });
}

// Init URL display on load
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
    """Return True if the error is a transient rate-limit or overload from the LLM provider."""
    s = str(exc).lower()
    return any(x in s for x in (
        "503", "429", "resource_exhausted", "overloaded",
        "rate limit", "quota", "too many requests",
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

    primary_provider = os.getenv("LLM_PROVIDER", "openai")
    fallback_provider = os.getenv("FALLBACK_LLM_PROVIDER")

    try:
        # Run the blocking graph pipeline in a thread so the async event loop
        # stays free for SSE heartbeats and other concurrent requests.
        result = await asyncio.to_thread(_run_pipeline, symbol, trade_date, analyst_list)
        return json.dumps(result, indent=2, default=str)

    except Exception as primary_exc:
        if fallback_provider and fallback_provider != primary_provider and _is_provider_limit_error(primary_exc):
            logger.warning(
                "Primary provider %s failed for %s (%s) — retrying with fallback %s",
                primary_provider, symbol, type(primary_exc).__name__, fallback_provider,
            )
            try:
                result = await asyncio.to_thread(
                    _run_pipeline, symbol, trade_date, analyst_list, fallback_provider
                )
                result["provider_used"] = fallback_provider
                result["primary_error"] = str(primary_exc)[:200]
                return json.dumps(result, indent=2, default=str)
            except Exception as fallback_exc:
                logger.exception("Fallback provider %s also failed for %s", fallback_provider, symbol)
                return json.dumps({
                    "symbol":          symbol,
                    "status":          "error",
                    "message":         str(fallback_exc),
                    "primary_error":   str(primary_exc)[:200],
                    "provider":        fallback_provider,
                    "primary_provider": primary_provider,
                    "hint": (
                        f"Both {primary_provider.upper()} and fallback {fallback_provider.upper()} failed. "
                        "Check API keys and quota."
                    ),
                })

        logger.exception("analyze_stock failed for %s", symbol)
        model = os.getenv("DEEP_THINK_LLM", "unknown")
        return json.dumps({
            "symbol":   symbol,
            "status":   "error",
            "message":  str(primary_exc),
            "provider": primary_provider,
            "model":    model,
            "hint":     (
                f"Check that the {primary_provider.upper()} API key is set and valid. "
                f"Current provider={primary_provider}, model={model}. "
                + (f"Set FALLBACK_LLM_PROVIDER env var to enable automatic failover." if not fallback_provider else "")
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
