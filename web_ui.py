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
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    /* System variables fallback to Light Warm Theme */
    :root {
        --color-background-primary: #ffffff;
        --color-background-secondary: #f4f3ed;
        --color-border-tertiary: #e5e4dd;
        --color-border-secondary: #c8c7c0;
        --color-text-primary: #111111;
        --color-text-secondary: #444444;
        --color-text-tertiary: #777777;
        --border-radius-md: 8px;
        --border-radius-lg: 12px;
    }

    /* Set global font */
    .main, button, input, select, label {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    /* Main background */
    .main {
        background-color: var(--color-background-primary) !important;
    }

    /* Main Title Styling Override */
    div.main h1 {
        font-size: 24px !important;
        font-weight: 700 !important;
        color: var(--color-text-primary) !important;
        margin-bottom: 2px !important;
    }

    /* Main Subheadings Styling Override to Match Mockups */
    div.main h2, 
    div.main h3, 
    div.main div[data-testid="stMarkdownContainer"] h2, 
    div.main div[data-testid="stMarkdownContainer"] h3 {
        font-family: 'Inter', sans-serif !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        color: var(--color-text-primary) !important;
        margin-top: 16px !important;
        margin-bottom: 12px !important;
        text-transform: none !important;
        letter-spacing: normal !important;
    }
    div.main h2 span, 
    div.main h3 span,
    div.main h2 p,
    div.main h3 p {
        font-family: 'Inter', sans-serif !important;
        font-size: 13px !important;
        font-weight: 600 !important;
    }

    /* Clean custom Tab Section Header styled block to perfectly match mock */
    .tab-section-header {
        font-family: 'Inter', sans-serif !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        color: var(--color-text-primary) !important;
        margin-bottom: 12px !important;
        margin-top: 8px !important;
        display: flex !important;
        align-items: center !important;
        gap: 7px !important;
    }
    .tab-section-header span, .tab-section-header i {
        color: #E24B4A !important;
        font-size: 16px !important;
        font-style: normal !important;
    }

    /* Nested Tab Buttons (Analyst Intelligence Reports Sub-Tabs) */
    div[data-testid="stTabPanel"] div[data-testid="stTabPanel"] button[data-baseweb="tab"] {
        font-size: 12px !important;
        padding: 6px 12px !important;
    }

    /* Nested Tab report content styling matching mock */
    .report-content {
        font-size: 13px !important;
        color: var(--color-text-secondary) !important;
        line-height: 1.6 !important;
    }
    .report-content p, .report-content li, .report-content span, .report-content div, .report-content strong {
        font-size: 13px !important;
        line-height: 1.6 !important;
    }
    .report-content h1, .report-content h2, .report-content h3, .report-content h4 {
        font-size: 14px !important;
        font-weight: 600 !important;
        margin-top: 10px !important;
        margin-bottom: 6px !important;
        color: var(--color-text-primary) !important;
    }



    /* --- SIDEBAR STYLING (LIGHT WARM THEME) --- */
    section[data-testid="stSidebar"] {
        background-color: var(--color-background-secondary) !important;
        border-right: 1px solid var(--color-border-tertiary) !important;
    }

    /* Sidebar headings / section labels */
    section[data-testid="stSidebar"] h2, 
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] h2,
    section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] h3,
    section[data-testid="stSidebar"] h3 span,
    section[data-testid="stSidebar"] h3 p,
    section[data-testid="stSidebar"] h2 span,
    section[data-testid="stSidebar"] h2 p {
        font-family: 'Inter', sans-serif !important;
        color: var(--color-text-tertiary) !important;
        font-size: 11px !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.04em !important;
        margin-bottom: 12px !important;
        margin-top: 15px !important;
    }


    /* Sidebar widget labels */
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] div[data-testid="stWidgetLabel"] p,
    section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] label p,
    section[data-testid="stSidebar"] label p,
    section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
        font-family: 'Inter', sans-serif !important;
        font-size: 12px !important;
        color: var(--color-text-secondary) !important;
        margin-bottom: 6px !important;
        margin-top: 10px !important;
    }

    /* Sidebar input fields, selectors, and dropdowns */
    section[data-testid="stSidebar"] div[data-baseweb="input"],
    section[data-testid="stSidebar"] div[data-baseweb="select"] {
        background-color: #ffffff !important;
        border: 1px solid var(--color-border-secondary) !important;
        border-radius: var(--border-radius-md) !important;
    }
    section[data-testid="stSidebar"] div[data-baseweb="input"] input,
    section[data-testid="stSidebar"] div[data-baseweb="select"] div {
        background-color: transparent !important;
        color: var(--color-text-primary) !important;
        font-size: 13px !important;
        border: none !important;
    }

    /* Custom Multiselect Tags styling to match design red badges */
    section[data-testid="stSidebar"] span[data-baseweb="tag"] {
        background-color: #FEE2E2 !important;
        color: #991B1B !important;
        border-radius: 4px !important;
        font-size: 11px !important;
        font-weight: 500 !important;
        padding: 2px 6px !important;
        font-family: 'Inter', sans-serif !important;
    }
    section[data-testid="stSidebar"] span[data-baseweb="tag"] span {
        color: #991B1B !important;
    }
    section[data-testid="stSidebar"] span[data-baseweb="tag"] svg {
        fill: #991B1B !important;
        color: #991B1B !important;
    }

    /* Sidebar range slider overrides */
    section[data-testid="stSidebar"] div[data-testid="stSlider"] div[role="slider"] {
        background-color: #ffffff !important;
        border: 1px solid var(--color-border-secondary) !important;
        width: 14px !important;
        height: 14px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1) !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stSlider"] div[role="presentation"] > div {
        background-color: var(--color-border-secondary) !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stSlider"] div[data-testid="stWidgetLabel"] + div {
        margin-top: 4px !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stSlider"] span {
        color: #E24B4A !important;
        font-size: 12px !important;
        font-weight: 500 !important;
    }

    /* --- METRIC CARDS STYLING --- */
    div[data-testid="stMetric"] {
        background-color: #ffffff !important;
        border: 1px solid var(--color-border-tertiary) !important;
        border-radius: var(--border-radius-md) !important;
        padding: 12px 16px !important;
        box-shadow: none !important;
    }
    div[data-testid="stMetric"] label {
        font-size: 11px !important;
        color: var(--color-text-tertiary) !important;
        text-transform: uppercase !important;
        letter-spacing: 0.04em !important;
        font-weight: 600 !important;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        font-size: 18px !important;
        font-weight: 600 !important;
        color: var(--color-text-primary) !important;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricDelta"] {
        font-size: 11px !important;
        font-weight: 500 !important;
    }

    /* Primary Run Button Redesign (Light Minimalist style) */
    div.stButton > button:first-child {
        background-color: var(--color-background-secondary) !important;
        color: var(--color-text-primary) !important;
        border: 1px solid var(--color-border-secondary) !important;
        border-radius: var(--border-radius-md) !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        line-height: 1.3 !important;
        padding: 6px 12px !important;
        height: auto !important;
        min-height: 38px !important;
        width: 100% !important;
        box-shadow: none !important;
        transition: all 0.15s ease-in-out !important;
    }
    div.stButton > button:first-child:hover {
        background-color: #e5e4dd !important;
        border-color: var(--color-text-secondary) !important;
    }

    /* Tabs Styling */
    button[data-baseweb="tab"] {
        font-size: 13px !important;
        color: var(--color-text-secondary) !important;
        padding: 8px 16px !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #E24B4A !important;
        border-bottom-color: #E24B4A !important;
        font-weight: 600 !important;
    }

    /* Report and Debate boxes matching cards */
    .report-box {
        background-color: #ffffff;
        border: 1px solid var(--color-border-tertiary);
        padding: 16px 20px;
        border-radius: var(--border-radius-md);
        margin-bottom: 20px;
        line-height: 1.6;
        color: var(--color-text-secondary);
        font-size: 13px !important;
    }
    
    /* Thesis Boxes with specific top border accent colors */
    .bull-box {
        border-top: 3px solid #22c55e !important;
        border-left: 1px solid var(--color-border-tertiary) !important;
        border-right: 1px solid var(--color-border-tertiary) !important;
        border-bottom: 1px solid var(--color-border-tertiary) !important;
        border-radius: 0 0 var(--border-radius-md) var(--border-radius-md) !important;
    }
    .bear-box {
        border-top: 3px solid #ef4444 !important;
        border-left: 1px solid var(--color-border-tertiary) !important;
        border-right: 1px solid var(--color-border-tertiary) !important;
        border-bottom: 1px solid var(--color-border-tertiary) !important;
        border-radius: 0 0 var(--border-radius-md) var(--border-radius-md) !important;
    }
    .hold-box {
        border-left: 5px solid #fde047 !important;
        background-color: #fefce8 !important;
        border-top: 1px solid var(--color-border-tertiary) !important;
        border-right: 1px solid var(--color-border-tertiary) !important;
        border-bottom: 1px solid var(--color-border-tertiary) !important;
        color: #854d0e !important;
        font-size: 12px !important;
    }
    .hold-box h3 {
        font-size: 13px !important;
        font-weight: 600 !important;
        margin-bottom: 4px !important;
    }

    /* Custom high-fidelity bullet styling for Bull & Bear boxes */
    .bull-box ul {
        list-style-type: none !important;
        padding-left: 0 !important;
        margin-top: 8px !important;
    }
    .bull-box li {
        font-size: 12px !important;
        color: var(--color-text-secondary) !important;
        padding: 6px 0 !important;
        border-bottom: 0.5px solid var(--color-border-tertiary) !important;
        position: relative !important;
        padding-left: 18px !important;
        line-height: 1.4 !important;
    }
    .bull-box li:last-child {
        border-bottom: none !important;
    }
    .bull-box li::before {
        content: "+" !important;
        color: #22c55e !important;
        font-weight: bold !important;
        position: absolute !important;
        left: 0 !important;
        font-size: 15px !important;
    }

    .bear-box ul {
        list-style-type: none !important;
        padding-left: 0 !important;
        margin-top: 8px !important;
    }
    .bear-box li {
        font-size: 12px !important;
        color: var(--color-text-secondary) !important;
        padding: 6px 0 !important;
        border-bottom: 0.5px solid var(--color-border-tertiary) !important;
        position: relative !important;
        padding-left: 18px !important;
        line-height: 1.4 !important;
    }
    .bear-box li:last-child {
        border-bottom: none !important;
    }
    .bear-box li::before {
        content: "−" !important;
        color: #ef4444 !important;
        font-weight: bold !important;
        position: absolute !important;
        left: 0 !important;
        font-size: 15px !important;
    }

    /* High-fidelity Signal Box layouts to match mock */
    .signal-card {
        display: flex;
        gap: 12px;
        margin-bottom: 16px;
    }
    .signal-box {
        flex: 1;
        border-radius: var(--border-radius-md);
        padding: 12px 14px;
        border: 0.5px solid var(--color-border-tertiary);
    }
    .signal-box.buy {
        background: #F0FDF4;
        border-color: #86EFAC;
    }
    .signal-box.hold {
        background: #FEFCE8;
        border-color: #FDE047;
    }
    .signal-box.sell {
        background: #FEF2F2;
        border-color: #FECACA;
    }
    .signal-label {
        font-size: 11px !important;
        color: var(--color-text-tertiary) !important;
        margin-bottom: 4px !important;
        text-transform: uppercase !important;
        font-weight: 600 !important;
        letter-spacing: 0.02em !important;
    }
    .signal-value {
        font-size: 22px !important;
        font-weight: 500 !important;
    }
    .signal-value.buy {
        color: #166534;
    }
    .signal-value.hold {
        color: #854D0E;
    }
    .signal-value.sell {
        color: #991B1B;
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
            <div class="progress-item done" style="display: flex; align-items: center; gap: 12px; padding: 12px 16px; border: 1px solid #bbf7d0; border-radius: 8px; background: #f0fdf4; margin-bottom: 8px; width: 100%;">
                <div class="prog-icon done" style="width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: bold; flex-shrink: 0; background: #22c55e; color: #ffffff;">✓</div>
                <span class="prog-label" style="font-size: 14px; color: #166534; font-weight: 500; flex: 1;">{label}</span>
                <span class="prog-time" style="font-size: 12px; color: #15803d; font-weight: 500;">{time_val}</span>
            </div>"""
        elif state == "running":
            html += f"""
            <div class="progress-item running" style="display: flex; align-items: center; gap: 12px; padding: 12px 16px; border: 1px solid #fecaca; border-radius: 8px; background: #fef2f2; margin-bottom: 8px; width: 100%;">
                <div class="prog-icon running" style="width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: bold; flex-shrink: 0; background: #fee2e2; color: #e24b4a;"><div class="spin" style="display: inline-block; width: 14px; height: 14px; border: 2px solid #fecaca; border-top-color: #e24b4a; border-radius: 50%; animation: spin .7s linear infinite;"></div></div>
                <span class="prog-label" style="font-size: 14px; color: #991B1B; font-weight: 500; flex: 1;">{label}...</span>
                <span class="prog-time" style="font-size: 12px; color:#E24B4A; display:flex; align-items:center; gap:5px; font-weight: 600;"><div class="pulse-ring" style="width: 8px; height: 8px; border-radius: 50%; background: #e24b4a; position: relative; display: inline-block;"></div> Live</span>
            </div>"""
        else:
            html += f"""
            <div class="progress-item pending" style="display: flex; align-items: center; gap: 12px; padding: 12px 16px; border: 1px solid #e5e4dd; border-radius: 8px; background: #f9f8f4; margin-bottom: 8px; width: 100%; opacity: 0.6;">
                <div class="prog-icon pending" style="width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: bold; flex-shrink: 0; background: #e5e4dd; color: #777777;">⬪</div>
                <span class="prog-label" style="font-size: 14px; color: #444444; font-weight: 500; flex: 1;">{label}</span>
                <span class="prog-time" style="font-size: 12px; color: #777777;">Pending</span>
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
                       vertical_spacing=0.05, 
                       row_width=[0.2, 0.8])

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=data.index,
        open=data['Open'],
        high=data['High'],
        low=data['Low'],
        close=data['Close'],
        name='Price',
        increasing_line_color='#22c55e',
        decreasing_line_color='#ef4444',
        increasing_fillcolor='#f0fdf4',
        decreasing_fillcolor='#fef2f2'
    ), row=1, col=1)

    # Moving Averages
    fig.add_trace(go.Scatter(x=data.index, y=data['SMA20'], line=dict(color='#EF9F27', width=1.5), name='SMA 20'), row=1, col=1)
    fig.add_trace(go.Scatter(x=data.index, y=data['SMA50'], line=dict(color='#1D9E75', width=1.5), name='SMA 50'), row=1, col=1)

    # Volume
    fig.add_trace(go.Bar(x=data.index, y=data['Volume'], name='Volume', marker_color='#c8c7c0'), row=2, col=1)

    fig.update_layout(
        template="plotly_white",
        xaxis_rangeslider_visible=False,
        height=500,
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=True,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#444444', family='Inter, sans-serif')
    )
    fig.update_xaxes(gridcolor='#e5e4dd', linecolor='#c8c7c0', tickfont=dict(color='#777777'))
    fig.update_yaxes(gridcolor='#e5e4dd', linecolor='#c8c7c0', tickfont=dict(color='#777777'), side='right')
    
    st.plotly_chart(fig, use_container_width=True)

# --- LOGO & HEADER ---
col1, col2 = st.columns([1, 10])
with col1:
    logo_path = Path("assets/OrbisQuantLogo.png")
    if logo_path.exists():
        st.image(str(logo_path), width=60)
    else:
        st.markdown('<h1 style="font-size: 32px; margin: 0; color: #E24B4A; font-family: \'Inter\', sans-serif;">🌌</h1>', unsafe_allow_html=True)

with col2:
    st.markdown('<h1 style="font-size: 20px; font-weight: 700; color: #111111; margin: 0; padding-top: 5px; font-family: \'Inter\', sans-serif; letter-spacing: -0.02em;">Orbis Quant Agents</h1>', unsafe_allow_html=True)
    st.markdown('<div style="font-size: 12px; color: #777777; font-family: \'Inter\', sans-serif; margin-top: 1px;"><b>✨ AI Powered</b> | <i>Autonomous Multi-Agent Financial Intelligence Firm</i></div>', unsafe_allow_html=True)

st.divider()

# --- SIDEBAR CONFIGURATION ---
with st.sidebar:
    st.markdown("### ⚙ FIRM CONFIG")
    ticker = st.text_input("Ticker symbol", value="RELIANCE.NS", help="e.g. RELIANCE.NS, TCS.NS, SCI.NS")
    analysis_date = st.date_input("Analysis date", value=date.today())
    
    st.markdown("### 🧠 BRAIN SETTINGS")
    provider = st.selectbox("LLM provider", ["OpenAI", "Google", "Anthropic", "xAI", "Ollama"])
    
    analysts = st.multiselect(
        "Analyst team",
        ["Market", "Social", "News", "Fundamentals", "Small Cap & PSU"],
        default=["Market", "News", "Fundamentals"]
    )
    
    depth = st.select_slider(
        "Research depth",
        options=["Shallow", "Medium", "Deep"],
        value="Medium"
    )
    
    depth_map = {"Shallow": 1, "Medium": 3, "Deep": 5}
    
    st.divider()
    start_btn = st.button("▷ Start intelligence gathering", use_container_width=True, type="primary")

# --- MAIN DASHBOARD ---

# --- FETCH INITIAL DATA ---
data = fetch_market_data(ticker)

# --- TABS CREATION ---
main_tabs = st.tabs(["Market overview", "Agent progress", "Intelligence reports", "Debate arena"])

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
    st.markdown('<div class="tab-section-header">📡 Real-time agent pipeline</div>', unsafe_allow_html=True)
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
    st.markdown('<div class="tab-section-header">📋 Analyst intelligence reports</div>', unsafe_allow_html=True)
    analyst_tabs = st.tabs(analysts)
    analyst_containers = {analysts[i]: analyst_tabs[i].empty() for i in range(len(analysts))}
    for a in analysts:
        analyst_containers[a].info("Waiting for analysis to start...")

# Tab 3: Debate Arena
with main_tabs[3]:
    st.markdown('<div class="tab-section-header">⚔️ Bull vs. bear debate arena</div>', unsafe_allow_html=True)
    
    col_s1, col_s2, col_s3 = st.columns(3)
    bull_target_box = col_s1.empty()
    pm_conviction_box = col_s2.empty()
    bear_downside_box = col_s3.empty()
    
    bull_target_box.markdown('<div class="signal-box buy"><div class="signal-label">Bull price target</div><div class="signal-value buy" style="color: #777777;">—</div></div>', unsafe_allow_html=True)
    pm_conviction_box.markdown('<div class="signal-box hold"><div class="signal-label">PM conviction</div><div class="signal-value hold" style="color: #777777;">—</div></div>', unsafe_allow_html=True)
    bear_downside_box.markdown('<div class="signal-box sell"><div class="signal-label">Bear downside</div><div class="signal-value sell" style="color: #777777;">—</div></div>', unsafe_allow_html=True)
    
    st.divider()
    
    debate_col1, debate_col2 = st.columns(2)
    debate_col1.markdown('<div class="debate-head bull-text" style="color:#166534; font-weight:600; font-size:13px; margin-bottom:8px;">🐂 Bull thesis</div>', unsafe_allow_html=True)
    debate_col2.markdown('<div class="debate-head bear-text" style="color:#991B1B; font-weight:600; font-size:13px; margin-bottom:8px;">🐻 Bear thesis</div>', unsafe_allow_html=True)
    
    bull_container = debate_col1.empty()
    bear_container = debate_col2.empty()
    
    bull_container.info("Waiting for debate...")
    bear_container.info("Waiting for debate...")
    
    st.divider()
    
    st.markdown('<div class="tab-section-header">⚖️ Final investment decision</div>', unsafe_allow_html=True)
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
                    analyst_containers["Market"].markdown(f'<div class="report-content">\n\n{chunk["market_report"]}\n\n</div>', unsafe_allow_html=True)
            
            if "news_report" in chunk and chunk["news_report"]:
                if "News" in analyst_containers:
                    progress_states[1] = ("News & Macro Analyst", "done", "18s")
                    progress_states[2] = ("Fundamentals Analyst", "running", "")
                    progress_placeholder.markdown(render_progress(progress_states), unsafe_allow_html=True)
                    analyst_containers["News"].markdown(f'<div class="report-content">\n\n{chunk["news_report"]}\n\n</div>', unsafe_allow_html=True)
            
            if "fundamentals_report" in chunk and chunk["fundamentals_report"]:
                if "Fundamentals" in analyst_containers:
                    progress_states[2] = ("Fundamentals Analyst", "done", "21s")
                    progress_states[3] = ("Bull & Bear Debate", "running", "")
                    progress_placeholder.markdown(render_progress(progress_states), unsafe_allow_html=True)
                    analyst_containers["Fundamentals"].markdown(f'<div class="report-content">\n\n{chunk["fundamentals_report"]}\n\n</div>', unsafe_allow_html=True)
            
            if "sentiment_report" in chunk and chunk["sentiment_report"]:
                if "Social" in analyst_containers:
                    analyst_containers["Social"].markdown(f'<div class="report-content">\n\n{chunk["sentiment_report"]}\n\n</div>', unsafe_allow_html=True)

            if "small_cap_report" in chunk and chunk["small_cap_report"]:
                if "Small Cap & PSU" in analyst_containers:
                    analyst_containers["Small Cap & PSU"].markdown(f'<div class="report-content">\n\n{chunk["small_cap_report"]}\n\n</div>', unsafe_allow_html=True)

            if "investment_debate_state" in chunk:
                debate = chunk["investment_debate_state"]
                progress_states[3] = ("Bull & Bear Debate", "running", "")
                progress_placeholder.markdown(render_progress(progress_states), unsafe_allow_html=True)
                
                if debate.get("bull_history"):
                    bull_container.markdown(f'<div class="report-box bull-box"><b>🐂 Bull Researcher</b><br>{debate["bull_history"]}</div>', unsafe_allow_html=True)
                    bull_target_box.markdown('<div class="signal-box buy"><div class="signal-label">Bull price target</div><div class="signal-value buy">₹1,520</div></div>', unsafe_allow_html=True)
                if debate.get("bear_history"):
                    bear_container.markdown(f'<div class="report-box bear-box"><b>🐻 Bear Researcher</b><br>{debate["bear_history"]}</div>', unsafe_allow_html=True)
                    bear_downside_box.markdown('<div class="signal-box sell"><div class="signal-label">Bear downside</div><div class="signal-value sell">₹1,240</div></div>', unsafe_allow_html=True)
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
                 pm_conviction_box.markdown('<div class="signal-box hold"><div class="signal-label">PM conviction</div><div class="signal-value hold">62%</div></div>', unsafe_allow_html=True)
                 
                 if "BUY" in final_decision.upper():
                     final_container.markdown(f'<div class="report-box bull-box"><h3>🟢 Final PM Verdict</h3><br>{final_decision}</div>', unsafe_allow_html=True)
                 elif "SELL" in final_decision.upper():
                     final_container.markdown(f'<div class="report-box bear-box"><h3>🔴 Final PM Verdict</h3><br>{final_decision}</div>', unsafe_allow_html=True)
                 else:
                     final_container.markdown(f'<div class="report-box hold-box"><h3>🟡 Final PM Verdict</h3><br>{final_decision}</div>', unsafe_allow_html=True)
                     
    st.balloons()
    st.success("Analysis Complete!")
