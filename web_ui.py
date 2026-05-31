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

if not start_btn:
    st.info("👈 Configure the firm and press 'Start' to begin analysis.")
    
    # Placeholder Chart for UI aesthetics
    st.subheader("📈 Market Overview")
    data = fetch_market_data(ticker)
    display_chart(data, ticker)

else:
    # --- ANALYSIS IN PROGRESS ---
    # Fetch data first for the main display
    st.subheader(f"📊 {ticker} Intelligence Feed")
    data = fetch_market_data(ticker)
    display_chart(data, ticker)
    
    # Mapping analysts to keys
    analyst_map = {
        "Market": "market",
        "Social": "social",
        "News": "news",
        "Fundamentals": "fundamentals",
        "Small Cap & PSU": "small_cap"
    }
    selected_keys = [analyst_map[a] for a in analysts]
    
    # Progress Section
    st.subheader("📡 Real-time Agent Progress")
    progress_cols = st.columns(len(analysts) + 3) # Analysts + Bull/Bear/PM
    
    agent_status = {a: st.empty() for a in analysts + ["Researcher", "Trader", "Portfolio Manager"]}
    for agent in agent_status:
        agent_status[agent].status(f"Pending: {agent}")

    # Results Containers
    chart_container = st.empty()
    
    st.divider()
    
    # Analyst Reports
    st.subheader("📋 Analyst Intelligence Reports")
    analyst_tabs = st.tabs(analysts)
    analyst_containers = {analysts[i]: analyst_tabs[i].empty() for i in range(len(analysts))}
    
    st.divider()
    
    # The Debate
    st.subheader("⚔️ Strategy Debate: Bull vs Bear")
    debate_col1, debate_col2 = st.columns(2)
    bull_container = debate_col1.empty()
    bear_container = debate_col2.empty()
    
    st.divider()
    
    # Final Decision
    st.subheader("⚖️ Final Investment Decision")
    final_container = st.empty()

    # --- EXECUTION ---
    
    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = depth_map[depth]
    config["max_risk_discuss_rounds"] = depth_map[depth]
    
    selected_provider = provider.lower()
    config["llm_provider"] = selected_provider
    
    # Load model overrides from environment variables
    config["deep_think_llm"] = os.getenv("DEEP_THINK_LLM", config["deep_think_llm"])
    config["quick_think_llm"] = os.getenv("QUICK_THINK_LLM", config["quick_think_llm"])
    
    # Clear the default OpenAI backend_url if the provider is not OpenAI
    if selected_provider != "openai":
        config["backend_url"] = None
    
    # Initialize Graph
    graph = OrbisQuantAgentsGraph(
        selected_analysts=selected_keys,
        config=config,
        debug=True
    )
    
    # Stream chunks
    init_state = graph.propagator.create_initial_state(ticker, analysis_date.strftime("%Y-%m-%d"))
    args = graph.propagator.get_graph_args()
    
    with st.spinner(f"Agents are gathering intelligence for {ticker}..."):
        for chunk in graph.graph.stream(init_state, **args):
            # Update Reports
            if "market_report" in chunk and chunk["market_report"]:
                if "Market" in analyst_containers:
                    agent_status["Market"].status("✅ Market Analyst Done", state="complete")
                    analyst_containers["Market"].markdown(chunk["market_report"])
            
            if "news_report" in chunk and chunk["news_report"]:
                if "News" in analyst_containers:
                    agent_status["News"].status("✅ News Analyst Done", state="complete")
                    analyst_containers["News"].markdown(chunk["news_report"])
            
            if "fundamentals_report" in chunk and chunk["fundamentals_report"]:
                if "Fundamentals" in analyst_containers:
                    agent_status["Fundamentals"].status("✅ Fundamentals Analyst Done", state="complete")
                    analyst_containers["Fundamentals"].markdown(chunk["fundamentals_report"])
            
            if "sentiment_report" in chunk and chunk["sentiment_report"]:
                if "Social" in analyst_containers:
                    agent_status["Social"].status("✅ Social Analyst Done", state="complete")
                    analyst_containers["Social"].markdown(chunk["sentiment_report"])

            if "small_cap_report" in chunk and chunk["small_cap_report"]:
                if "Small Cap & PSU" in analyst_containers:
                    agent_status["Small Cap & PSU"].status("✅ Small Cap Analyst Done", state="complete")
                    analyst_containers["Small Cap & PSU"].markdown(chunk["small_cap_report"])

            # Update Debate
            if "investment_debate_state" in chunk:
                debate = chunk["investment_debate_state"]
                agent_status["Researcher"].status("🏃 Researchers Debating...", state="running")
                if debate.get("bull_history"):
                    bull_container.markdown(f'<div class="report-box bull-box"><b>🐂 Bull Researcher</b><br>{debate["bull_history"]}</div>', unsafe_allow_html=True)
                if debate.get("bear_history"):
                    bear_container.markdown(f'<div class="report-box bear-box"><b>🐻 Bear Researcher</b><br>{debate["bear_history"]}</div>', unsafe_allow_html=True)
                if debate.get("judge_decision"):
                    agent_status["Researcher"].status("✅ Researcher Team Done", state="complete")

            # Update Final
            if "final_trade_decision" in chunk and chunk["final_trade_decision"]:
                 agent_status["Portfolio Manager"].status("✅ Analysis Complete", state="complete")
                 final_container.success(f"### {chunk['final_trade_decision']}")

    st.balloons()
    st.success("Analysis Complete! Download reports from the Sidebar.")
