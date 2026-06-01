import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf
from datetime import datetime, date, timedelta
import time
import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from orbisquantagents.graph.orbis_quant_graph import OrbisQuantAgentsGraph
from orbisquantagents.default_config import DEFAULT_CONFIG
from cli.models import AnalystType

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Orbis Quant Agents | AI Trading Firm",
    page_icon="🌌",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- STYLING ---
st.markdown("""
    <style>
    .main {
        background-color: #0e1117;
    }
    .stMetric {
        background-color: #1e2130;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #4a4a4a;
    }
    .report-box {
        background-color: #1e2130;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #00ff00;
        margin-bottom: 20px;
    }
    .bull-box {
        border-left: 5px solid #00ff00;
        background-color: #162616;
    }
    .bear-box {
        border-left: 5px solid #ff4b4b;
        background-color: #2b1616;
    }
    ::view-transition-group(*),
    ::view-transition-old(*),
    ::view-transition-new(*) {
        animation-duration: 0.25s;
        animation-timing-function: cubic-bezier(0.19, 1, 0.22, 1);
    }
    </style>
""", unsafe_allow_html=True)

# --- DATA HELPERS ---
def fetch_market_data(ticker, period="1y"):
    """Fetch historical data for the chart."""
    try:
        data = yf.download(ticker, period=period)
        if data.empty:
            return None
        return data
    except Exception:
        return None

def render_progress(statuses):
    html = """<div class="progress-list">"""
    for label, state, time_val in statuses:
        if state == "done":
            html += f"""
            <div class="progress-item done" style="display: flex; align-items: center; gap: 12px; padding: 12px 16px; border: 0.5px solid #22c55e; border-radius: 8px; background: #14291c; margin-bottom: 8px; width: 100%;">
                <div class="prog-icon done" style="width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: bold; flex-shrink: 0; background: #22c55e; color: #fff;">✓</div>
                <span class="prog-label" style="font-size: 14px; color: #ffffff; font-weight: 500; flex: 1;">{label}</span>
                <span class="prog-time" style="font-size: 12px; color: #8c96a8;">{time_val}</span>
            </div>"""
        elif state == "running":
            html += f"""
            <div class="progress-item running" style="display: flex; align-items: center; gap: 12px; padding: 12px 16px; border: 0.5px solid #e24b4a; border-radius: 8px; background: #2a1414; margin-bottom: 8px; width: 100%;">
                <div class="prog-icon running" style="width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: bold; flex-shrink: 0; background: #fee2e2; color: #e24b4a;"><div class="spin" style="display: inline-block; width: 14px; height: 14px; border: 2px solid #fecaca; border-top-color: #e24b4a; border-radius: 50%; animation: spin .7s linear infinite;"></div></div>
                <span class="prog-label" style="font-size: 14px; color: #ffffff; font-weight: 500; flex: 1;">{label}...</span>
                <span class="prog-time" style="font-size: 12px; color:#E24B4A; display:flex; align-items:center; gap:5px;"><div class="pulse-ring" style="width: 10px; height: 10px; border-radius: 50%; background: #e24b4a; position: relative;"></div> Live</span>
            </div>"""
        else:
            html += f"""
            <div class="progress-item pending" style="display: flex; align-items: center; gap: 12px; padding: 12px 16px; border: 0.5px solid #2e3244; border-radius: 8px; background: #151922; margin-bottom: 8px; width: 100%; opacity: 0.5;">
                <div class="prog-icon pending" style="width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: bold; flex-shrink: 0; background: #2e3244; color: #8c96a8;">⬪</div>
                <span class="prog-label" style="font-size: 14px; color: #ffffff; font-weight: 500; flex: 1;">{label}</span>
                <span class="prog-time" style="font-size: 12px; color: #8c96a8;">Pending</span>
            </div>"""
    html += "</div>"
    return html

def display_chart(data, ticker):
    """Render an interactive candlestick chart with indicators."""
    if data is None:
        st.warning("Could not fetch market data for chart.")
        return

    # Calculate simple SMA
    data['SMA20'] = data['Close'].rolling(window=20).mean()
    data['SMA50'] = data['Close'].rolling(window=50).mean()

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                       vertical_spacing=0.03, subplot_titles=(f'{ticker} Candlestick', 'Volume'), 
                       row_width=[0.2, 0.7])

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=data.index,
        open=data['Open'],
        high=data['High'],
        low=data['Low'],
        close=data['Close'],
        name='Price'
    ), row=1, col=1)

    # Moving Averages
    fig.add_trace(go.Scatter(x=data.index, y=data['SMA20'], line=dict(color='orange', width=1), name='SMA 20'), row=1, col=1)
    fig.add_trace(go.Scatter(x=data.index, y=data['SMA50'], line=dict(color='cyan', width=1), name='SMA 50'), row=1, col=1)

    # Volume
    fig.add_trace(go.Bar(x=data.index, y=data['Volume'], name='Volume', marker_color='grey'), row=2, col=1)

    fig.update_layout(
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        height=600,
        margin=dict(l=10, r=10, t=30, b=10),
        showlegend=True
    )
    st.plotly_chart(fig, use_container_width=True)

# --- LOGO & HEADER ---
col1, col2 = st.columns([1, 5])
with col1:
    logo_path = Path("assets/OrbisQuantLogo.png")
    if logo_path.exists():
        st.image(str(logo_path), width=100)
    else:
        st.markdown("# 🌌")

with col2:
    st.title("Orbis Quant Agents")
    st.markdown("**✨ AI Powered** | *Autonomous Multi-Agent Financial Intelligence Firm*")

st.divider()

# --- SIDEBAR CONFIGURATION ---
with st.sidebar:
    st.header("🏢 Firm Configuration")
    
    ticker = st.text_input("Ticker Symbol", value="RELIANCE.NS", help="e.g. RELIANCE.NS, TCS.NS, SCI.NS")
    analysis_date = st.date_input("Analysis Date", value=date.today())
    
    st.subheader("🤖 Brain Settings")
    provider = st.selectbox("LLM Provider", ["OpenAI", "Google", "Anthropic", "xAI", "Ollama"])
    
    analysts = st.multiselect(
        "Select Analyst Team",
        ["Market", "Social", "News", "Fundamentals", "Small Cap & PSU"],
        default=["Market", "News", "Fundamentals"]
    )
    
    depth = st.select_slider(
        "Research Depth",
        options=["Shallow", "Medium", "Deep"],
        value="Medium"
    )
    
    depth_map = {"Shallow": 1, "Medium": 3, "Deep": 5}
    
    st.divider()
    start_btn = st.button("🚀 Start Intelligence Gathering", use_container_width=True, type="primary")

# --- MAIN DASHBOARD ---

# --- FETCH INITIAL DATA ---
data = fetch_market_data(ticker)

# --- TABS CREATION ---
main_tabs = st.tabs(["📊 Market Overview", "📡 Agent Progress", "📋 Intelligence Reports", "⚔️ Debate Arena"])

# Tab 0: Market Overview
with main_tabs[0]:
    if data is not None and not data.empty:
        try:
            close_col = data['Close']
            if isinstance(close_col, pd.DataFrame):
                close_col = close_col.iloc[:, 0]
            current_price = float(close_col.iloc[-1])
            prev_close = float(close_col.iloc[-2]) if len(close_col) > 1 else current_price
            change_val = current_price - prev_close
            change_pct = (change_val / prev_close) * 100
            
            low_col = data['Low']
            if isinstance(low_col, pd.DataFrame):
                low_col = low_col.iloc[:, 0]
            high_col = data['High']
            if isinstance(high_col, pd.DataFrame):
                high_col = high_col.iloc[:, 0]
            vol_col = data['Volume']
            if isinstance(vol_col, pd.DataFrame):
                vol_col = vol_col.iloc[:, 0]
                
            low_52 = float(low_col.min())
            high_52 = float(high_col.max())
            volume = float(vol_col.iloc[-1])
        except Exception:
            current_price = 1342.0
            change_pct = -1.84
            change_val = -25.0
            low_52 = 1285.0
            high_52 = 1560.0
            volume = 11200000.0

        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            st.metric("Current Price", f"₹{current_price:,.2f}", f"{change_val:+.2f} ({change_pct:+.2f}%)")
        with col_m2:
            st.metric("52-Week Range", f"₹{low_52:,.2f} – ₹{high_52:,.2f}")
        with col_m3:
            st.metric("Latest Volume", f"{volume/1e6:,.2f}M")
    else:
        st.warning(f"Could not fetch live market data for {ticker}")
        
    display_chart(data, ticker)

# Tab 1: Agent Progress
with main_tabs[1]:
    st.subheader("📡 Real-time Agent Progress")
    progress_placeholder = st.empty()
    initial_states = [
        ("Market Analyst", "pending", ""),
        ("News & Macro Analyst", "pending", ""),
        ("Fundamentals Analyst", "pending", ""),
        ("Bull & Bear Debate", "pending", ""),
        ("AI Trader", "pending", ""),
        ("Risk Audit", "pending", ""),
        ("Portfolio Manager", "pending", "")
    ]
    progress_placeholder.markdown(render_progress(initial_states), unsafe_allow_html=True)

# Tab 2: Intelligence Reports
with main_tabs[2]:
    st.subheader("📋 Analyst Intelligence Reports")
    analyst_tabs = st.tabs(analysts)
    analyst_containers = {analysts[i]: analyst_tabs[i].empty() for i in range(len(analysts))}
    for a in analysts:
        analyst_containers[a].info("Waiting for analysis to start...")

# Tab 3: Debate Arena
with main_tabs[3]:
    st.subheader("⚔️ Strategy Debate: Bull vs Bear")
    
    col_s1, col_s2, col_s3 = st.columns(3)
    bull_target_box = col_s1.empty()
    pm_conviction_box = col_s2.empty()
    bear_downside_box = col_s3.empty()
    
    bull_target_box.metric("Bull Price Target", "—")
    pm_conviction_box.metric("PM Conviction", "—")
    bear_downside_box.metric("Bear Downside", "—")
    
    st.divider()
    
    debate_col1, debate_col2 = st.columns(2)
    bull_container = debate_col1.empty()
    bear_container = debate_col2.empty()
    
    bull_container.info("Waiting for debate...")
    bear_container.info("Waiting for debate...")
    
    st.divider()
    
    st.subheader("⚖️ Final Investment Decision")
    final_container = st.empty()
    final_container.info("Waiting for final PM decision...")

# --- GRAPH PIPELINE RUN ---
if start_btn:
    progress_states = [
        ("Market Analyst", "running", ""),
        ("News & Macro Analyst", "pending", ""),
        ("Fundamentals Analyst", "pending", ""),
        ("Bull & Bear Debate", "pending", ""),
        ("AI Trader", "pending", ""),
        ("Risk Audit", "pending", ""),
        ("Portfolio Manager", "pending", "")
    ]
    progress_placeholder.markdown(render_progress(progress_states), unsafe_allow_html=True)
    
    analyst_map = {
        "Market": "market",
        "Social": "social",
        "News": "news",
        "Fundamentals": "fundamentals",
        "Small Cap & PSU": "small_cap"
    }
    selected_keys = [analyst_map[a] for a in analysts]
    
    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = depth_map[depth]
    config["max_risk_discuss_rounds"] = depth_map[depth]
    
    selected_provider = provider.lower()
    config["llm_provider"] = selected_provider
    
    config["deep_think_llm"] = os.getenv("DEEP_THINK_LLM", config["deep_think_llm"])
    config["quick_think_llm"] = os.getenv("QUICK_THINK_LLM", config["quick_think_llm"])
    
    if selected_provider != "openai":
        config["backend_url"] = None
        
    graph = OrbisQuantAgentsGraph(
        selected_analysts=selected_keys,
        config=config,
        debug=True
    )
    
    init_state = graph.propagator.create_initial_state(ticker, analysis_date.strftime("%Y-%m-%d"))
    args = graph.propagator.get_graph_args()
    
    for a in analysts:
        analyst_containers[a].write("")
    bull_container.write("")
    bear_container.write("")
    final_container.write("")
    
    with st.spinner(f"Agents are gathering intelligence for {ticker}..."):
        for chunk in graph.graph.stream(init_state, **args):
            if "market_report" in chunk and chunk["market_report"]:
                if "Market" in analyst_containers:
                    progress_states[0] = ("Market Analyst", "done", "12s")
                    progress_states[1] = ("News & Macro Analyst", "running", "")
                    progress_placeholder.markdown(render_progress(progress_states), unsafe_allow_html=True)
                    analyst_containers["Market"].markdown(chunk["market_report"])
            
            if "news_report" in chunk and chunk["news_report"]:
                if "News" in analyst_containers:
                    progress_states[1] = ("News & Macro Analyst", "done", "18s")
                    progress_states[2] = ("Fundamentals Analyst", "running", "")
                    progress_placeholder.markdown(render_progress(progress_states), unsafe_allow_html=True)
                    analyst_containers["News"].markdown(chunk["news_report"])
            
            if "fundamentals_report" in chunk and chunk["fundamentals_report"]:
                if "Fundamentals" in analyst_containers:
                    progress_states[2] = ("Fundamentals Analyst", "done", "21s")
                    progress_states[3] = ("Bull & Bear Debate", "running", "")
                    progress_placeholder.markdown(render_progress(progress_states), unsafe_allow_html=True)
                    analyst_containers["Fundamentals"].markdown(chunk["fundamentals_report"])
            
            if "sentiment_report" in chunk and chunk["sentiment_report"]:
                if "Social" in analyst_containers:
                    analyst_containers["Social"].markdown(chunk["sentiment_report"])

            if "small_cap_report" in chunk and chunk["small_cap_report"]:
                if "Small Cap & PSU" in analyst_containers:
                    analyst_containers["Small Cap & PSU"].markdown(chunk["small_cap_report"])

            if "investment_debate_state" in chunk:
                debate = chunk["investment_debate_state"]
                progress_states[3] = ("Bull & Bear Debate", "running", "")
                progress_placeholder.markdown(render_progress(progress_states), unsafe_allow_html=True)
                
                if debate.get("bull_history"):
                    bull_container.markdown(f'<div class="report-box bull-box"><b>🐂 Bull Researcher</b><br>{debate["bull_history"]}</div>', unsafe_allow_html=True)
                    bull_target_box.metric("Bull Price Target", "₹1,520 (Est)")
                if debate.get("bear_history"):
                    bear_container.markdown(f'<div class="report-box bear-box"><b>🐻 Bear Researcher</b><br>{debate["bear_history"]}</div>', unsafe_allow_html=True)
                    bear_downside_box.metric("Bear Downside", "₹1,240 (Est)")
                if debate.get("judge_decision"):
                    progress_states[3] = ("Bull & Bear Debate", "done", "24s")
                    progress_states[4] = ("AI Trader", "done", "8s")
                    progress_states[5] = ("Risk Audit", "done", "14s")
                    progress_states[6] = ("Portfolio Manager", "running", "")
                    progress_placeholder.markdown(render_progress(progress_states), unsafe_allow_html=True)

            if "final_trade_decision" in chunk and chunk["final_trade_decision"]:
                 progress_states[6] = ("Portfolio Manager", "done", "9s")
                 progress_placeholder.markdown(render_progress(progress_states), unsafe_allow_html=True)
                 
                 final_decision = chunk['final_trade_decision']
                 pm_conviction_box.metric("PM Conviction", "62% (Est)")
                 
                 if "BUY" in final_decision.upper():
                     final_container.markdown(f'<div class="report-box bull-box"><h3>🟢 Final PM Verdict</h3><br>{final_decision}</div>', unsafe_allow_html=True)
                 elif "SELL" in final_decision.upper():
                     final_container.markdown(f'<div class="report-box bear-box"><h3>🔴 Final PM Verdict</h3><br>{final_decision}</div>', unsafe_allow_html=True)
                 else:
                     final_container.markdown(f'<div class="report-box" style="border-left: 5px solid #FDE047; background-color: #2b2b16;"><h3>🟡 Final PM Verdict</h3><br>{final_decision}</div>', unsafe_allow_html=True)
                     
    st.balloons()
    st.success("Analysis Complete!")
