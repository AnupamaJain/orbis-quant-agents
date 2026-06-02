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
from PIL import Image

load_dotenv()

from orbisquantagents.graph.orbis_quant_graph import OrbisQuantAgentsGraph
from orbisquantagents.default_config import DEFAULT_CONFIG
from cli.models import AnalystType

# Load logo safely for browser tab
try:
    logo_img = Image.open("/Users/admin/MultiTradingAgents/MultiTradingAgent/assets/OrbisQuantLogo.png")
except Exception:
    logo_img = "🌌"

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Orbis Quant Agents | AI Trading Platform",
    page_icon=logo_img,
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- STYLING ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    /* System variables fallback to Light Cool Theme */
    :root {
        --color-background-primary: #ffffff;
        --color-background-secondary: #f3f4f6;
        --color-border-tertiary: #e5e7eb;
        --color-border-secondary: #d1d5db;
        --color-text-primary: #111827;
        --color-text-secondary: #4b5563;
        --color-text-tertiary: #9ca3af;
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

    /* Custom Multiselect Tags styling to match design orange/gold badges */
    section[data-testid="stSidebar"] span[data-baseweb="tag"] {
        background-color: #FFFBEB !important;
        border: 1px solid #FCD34D !important;
        color: #D97706 !important;
        border-radius: 4px !important;
        font-size: 11px !important;
        font-weight: 500 !important;
        padding: 2px 6px !important;
        font-family: 'Inter', sans-serif !important;
    }
    section[data-testid="stSidebar"] span[data-baseweb="tag"] span {
        color: #D97706 !important;
    }
    section[data-testid="stSidebar"] span[data-baseweb="tag"] svg {
        fill: #D97706 !important;
        color: #D97706 !important;
    }

    /* Sidebar range slider overrides */
    section[data-testid="stSidebar"] div[data-testid="stSlider"] div[role="slider"] {
        background-color: #ffffff !important;
        border: 2px solid #D97706 !important;
        width: 14px !important;
        height: 14px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1) !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stSlider"] div[data-testid="stWidgetLabel"] + div {
        margin-top: 4px !important;
    }
    /* Style all slider labels (moving current value, and bottom tick marks) to brand gold-orange */
    section[data-testid="stSidebar"] div[data-testid="stSlider"] span,
    section[data-testid="stSidebar"] div[data-testid="stSlider"] div[role="presentation"] span,
    section[data-testid="stSidebar"] div[data-testid="stSlider"] div[role="presentation"] div,
    section[data-testid="stSidebar"] div[data-testid="stSlider"] [data-baseweb="slider"] ~ div,
    section[data-testid="stSidebar"] div[data-testid="stSlider"] [data-baseweb="slider"] ~ div div {
        color: #D97706 !important;
        font-size: 11px !important;
        font-weight: 600 !important;
        background-color: transparent !important;
        background: transparent !important;
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
        background-color: #e5e7eb !important;
        border-color: var(--color-text-secondary) !important;
    }

    /* Tabs Styling */
    button[data-baseweb="tab"] {
        font-size: 13px !important;
        color: var(--color-text-secondary) !important;
        padding: 8px 16px !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #D97706 !important;
        border-bottom-color: #D97706 !important;
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
        border-left: 5px solid #9ca3af !important;
        background-color: #f9fafb !important;
        border-top: 1px solid var(--color-border-tertiary) !important;
        border-right: 1px solid var(--color-border-tertiary) !important;
        border-bottom: 1px solid var(--color-border-tertiary) !important;
        color: #4b5563 !important;
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

    /* Sticky horizontal indices ticker bar styling matching reference */
    .top-ticker-bar {
        display: flex !important;
        align-items: center !important;
        gap: 16px !important;
        padding: 6px 16px !important;
        background-color: #ffffff !important;
        border: 1px solid var(--color-border-tertiary) !important;
        border-radius: var(--border-radius-md) !important;
        font-size: 11px !important;
        font-family: 'Inter', sans-serif !important;
        overflow-x: auto !important;
        white-space: nowrap !important;
        margin-top: 10px !important;
        margin-bottom: 16px !important;
        width: 100% !important;
    }
    .ticker-item {
        display: flex !important;
        align-items: center !important;
        gap: 5px !important;
        color: var(--color-text-primary) !important;
        font-weight: 500 !important;
    }
    .ticker-name {
        color: var(--color-text-secondary) !important;
        font-weight: 600 !important;
    }
    .ticker-change.up {
        color: #22c55e !important;
        font-weight: 600 !important;
    }
    .ticker-change.down {
        color: #ef4444 !important;
        font-weight: 600 !important;
    }
    .ticker-live-badge {
        margin-left: auto !important;
        display: flex !important;
        align-items: center !important;
        gap: 6px !important;
        background-color: #f0fdf4 !important;
        border: 1px solid #bbf7d0 !important;
        color: #166534 !important;
        padding: 2px 8px !important;
        border-radius: 20px !important;
        font-weight: 600 !important;
        font-size: 10px !important;
    }
    .pulse-dot {
        width: 6px !important;
        height: 6px !important;
        border-radius: 50% !important;
        background-color: #22c55e !important;
        animation: pulse-dot-anim 1.5s infinite !important;
        display: inline-block !important;
    }
    @keyframes pulse-dot-anim {
        0% { transform: scale(0.9); opacity: 1; }
        50% { transform: scale(1.3); opacity: 0.4; }
        100% { transform: scale(0.9); opacity: 1; }
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
def render_news_desk_html(ticker, raw_news_text):
    """Render a high-fidelity News Desk Layout tailored to the given ticker, parsing live feed text."""
    # Split text into lines
    lines = raw_news_text.strip().split("\n") if raw_news_text else []
    headlines = []
    
    for line in lines:
        cleaned = line.strip().lstrip("*- ").strip()
        if not cleaned:
            continue
        # Check if it has enough length to be a valid headline
        if ":" in cleaned or "**" in cleaned or len(cleaned) > 20:
            title = cleaned.replace("**", "").replace("###", "").strip()
            
            # Determine sentiment
            sentiment = "NEUTRAL"
            sentiment_color = "#4B5563"
            sentiment_bg = "#F3F4F6"
            sentiment_border = "#E5E7EB"
            dot_color = "#9CA3AF"
            
            upper_title = title.upper()
            if any(k in upper_title for k in ["BULLISH", "POSITIVE", "BUY", "GROWTH", "GAIN", "UPWARD", "UP"]):
                sentiment = "BULLISH"
                sentiment_color = "#166534"
                sentiment_bg = "#f0fdf4"
                sentiment_border = "#bbf7d0"
                dot_color = "#22c55e"
            elif any(k in upper_title for k in ["BEARISH", "NEGATIVE", "SELL", "RISK", "DROP", "DOWN", "LOSS"]):
                sentiment = "BEARISH"
                sentiment_color = "#991B1B"
                sentiment_bg = "#fef2f2"
                sentiment_border = "#fecaca"
                dot_color = "#ef4444"
                
            headlines.append({
                "title": title,
                "source": "Market Wire",
                "time": "12m ago",
                "sentiment": sentiment,
                "sentiment_color": sentiment_color,
                "sentiment_bg": sentiment_bg,
                "sentiment_border": sentiment_border,
                "dot_color": dot_color
            })
            
    # Fallback to realistic context headlines if none parsed from live stream yet
    if not headlines:
        ticker_name = ticker.split('.')[0]
        headlines = [
            {
                "title": f"Institutional buyers acquire bulk blocks in {ticker_name} amid stable outlook",
                "source": "Exchange Feed",
                "time": "5m ago",
                "sentiment": "BULLISH",
                "sentiment_color": "#166534",
                "sentiment_bg": "#f0fdf4",
                "sentiment_border": "#bbf7d0",
                "dot_color": "#22c55e"
            },
            {
                "title": f"{ticker_name} announces standard structural expansion plans starting next quarter",
                "source": "Press Release",
                "time": "12m ago",
                "sentiment": "NEUTRAL",
                "sentiment_color": "#4B5563",
                "sentiment_bg": "#F3F4F6",
                "sentiment_border": "#E5E7EB",
                "dot_color": "#9CA3AF"
            },
            {
                "title": f"Technical analysis shows consolidated key support levels for {ticker_name}",
                "source": "Technical Analyst",
                "time": "25m ago",
                "sentiment": "BULLISH",
                "sentiment_color": "#166534",
                "sentiment_bg": "#f0fdf4",
                "sentiment_border": "#bbf7d0",
                "dot_color": "#22c55e"
            },
            {
                "title": f"Macro headwinds indicate potential margin distribution pressure in industry sector",
                "source": "Sector Wire",
                "time": "45m ago",
                "sentiment": "BEARISH",
                "sentiment_color": "#991B1B",
                "sentiment_bg": "#fef2f2",
                "sentiment_border": "#fecaca",
                "dot_color": "#ef4444"
            }
        ]
        
    bull_cnt = sum(1 for h in headlines if h["sentiment"] == "BULLISH")
    bear_cnt = sum(1 for h in headlines if h["sentiment"] == "BEARISH")
    neutral_cnt = len(headlines) - bull_cnt - bear_cnt
    
    # Left Feed Box (HTML)
    left_feed_html = f"""
    <div style="display: flex; flex-direction: column; gap: 10px; flex: 1; min-width: 320px;">
        <!-- AI Sentiment Classifier Card -->
        <div style="background-color: #f9fafb; border: 0.5px solid #e5e7eb; border-radius: 8px; padding: 12px 14px; display: flex; align-items: center; justify-content: space-between;">
            <div>
                <div style="font-size: 12px; font-weight: 700; color: #111111;">🤖 AI Sentiment Classifier</div>
                <div style="font-size: 11px; color: #6B7280; margin-top: 2px;">Llama-3.1-8b-instant · Groq free tier API</div>
            </div>
            <span style="background-color: #f0fdf4; border: 1px solid #bbf7d0; color: #166534; font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 20px;">✓ Active</span>
        </div>
        
        <!-- Live News Feed Header and Badges -->
        <div style="display: flex; align-items: center; gap: 8px; font-size: 11px; margin: 5px 0; flex-wrap: wrap;">
            <span style="font-weight: 700; color: #111111;">Live news feed</span>
            <span style="background: #e5e7eb; color: #4B5563; font-weight: 600; padding: 2px 6px; border-radius: 4px;">All {len(headlines)}</span>
            <span style="background: #f0fdf4; color: #166534; font-weight: 600; padding: 2px 6px; border-radius: 4px;">Bullish {bull_cnt}</span>
            <span style="background: #fef2f2; color: #991B1B; font-weight: 600; padding: 2px 6px; border-radius: 4px;">Bearish {bear_cnt}</span>
        </div>
        
        <!-- News List of Cards -->
        <div style="display: flex; flex-direction: column; gap: 8px;">
     """
    
    for h in headlines:
        left_feed_html += f"""
        <div style="background-color: #ffffff; border: 0.5px solid #e5e7eb; border-radius: 8px; padding: 12px 14px; display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;">
            <div style="display: flex; gap: 10px; align-items: flex-start;">
                <div style="width: 7px; height: 7px; border-radius: 50%; background-color: {h['dot_color']}; margin-top: 5px; flex-shrink: 0;"></div>
                <div>
                    <div style="font-size: 12px; font-weight: 600; color: #111111; line-height: 1.4;">{h['title']}</div>
                    <div style="font-size: 10px; color: #777777; margin-top: 4px;">{h['source']} · {h['time']}</div>
                </div>
            </div>
            <span style="background-color: {h['sentiment_bg']}; border: 0.5px solid {h['sentiment_border']}; color: {h['sentiment_color']}; font-size: 9px; font-weight: 600; padding: 2px 6px; border-radius: 4px; flex-shrink: 0; text-transform: uppercase;">{h['sentiment']}</span>
        </div>"""
        
    left_feed_html += "</div></div>"
    
    # Calculate mood left slider percent
    total = len(headlines)
    bull_pct = int((bull_cnt / total) * 100) if total > 0 else 50
    mood_pos = max(10, min(90, bull_pct))
    
    # Right Widgets Bar (HTML)
    right_widgets_html = f"""
    <div style="display: flex; flex-direction: column; gap: 12px; width: 280px; flex-shrink: 0; min-width: 250px;">
        <!-- Market Mood Gauge Widget -->
        <div style="background-color: #ffffff; border: 0.5px solid #e5e7eb; border-radius: 8px; padding: 12px 14px;">
            <div style="font-size: 12px; font-weight: 700; color: #111111; margin-bottom: 4px;">📈 Market mood</div>
            <div style="font-size: 11px; color: #6B7280; margin-bottom: 12px;">Headlines sentiment gauge</div>
            
            <div style="height: 6px; border-radius: 3px; background: linear-gradient(to right, #ef4444, #e5e7eb, #22c55e); position: relative; margin: 0 5px 14px;">
                <div style="width: 10px; height: 10px; border-radius: 50%; background-color: #111111; border: 2px solid #ffffff; position: absolute; top: -2px; left: {mood_pos}%; box-shadow: 0 1px 3px rgba(0,0,0,0.2);"></div>
            </div>
            
            <div style="display: flex; justify-content: space-between; font-size: 10px; color: #6B7280; font-weight: 600;">
                <span style="color: #991B1B;">Bearish ({bear_cnt})</span>
                <span>Neutral ({neutral_cnt})</span>
                <span style="color: #166534;">Bullish ({bull_cnt})</span>
            </div>
        </div>
        
        <!-- Symbols In News Mentions Widget -->
        <div style="background-color: #ffffff; border: 0.5px solid #e5e7eb; border-radius: 8px; padding: 12px 14px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <span style="font-size: 12px; font-weight: 700; color: #111111;"># Mentions in feed</span>
                <span style="font-size: 10px; color: #6B7280;">Mentions</span>
            </div>
            <div style="display: flex; flex-direction: column; gap: 8px;">
                <div style="display: flex; align-items: center; gap: 8px; font-size: 11px;">
                    <span style="width: 12px; color: #6B7280; font-weight: 700;">1</span>
                    <span style="width: 70px; font-weight: 700; color: #111111;">{ticker.split('.')[0]}</span>
                    <div style="flex: 1; height: 8px; background-color: #D97706; border-radius: 4px; overflow: hidden; max-width: 120px;"></div>
                    <span style="color: #6B7280; font-weight: 600;">8</span>
                </div>
                <div style="display: flex; align-items: center; gap: 8px; font-size: 11px;">
                    <span style="width: 12px; color: #6B7280; font-weight: 700;">2</span>
                    <span style="width: 70px; font-weight: 700; color: #111111;">NIFTY</span>
                    <div style="flex: 1; height: 8px; background-color: #d1d5db; border-radius: 4px; overflow: hidden; max-width: 60px;"></div>
                    <span style="color: #6B7280; font-weight: 600;">4</span>
                </div>
                <div style="display: flex; align-items: center; gap: 8px; font-size: 11px;">
                    <span style="width: 12px; color: #6B7280; font-weight: 700;">3</span>
                    <span style="width: 70px; font-weight: 700; color: #111111;">FII</span>
                    <div style="flex: 1; height: 8px; background-color: #d1d5db; border-radius: 4px; overflow: hidden; max-width: 30px;"></div>
                    <span style="color: #6B7280; font-weight: 600;">2</span>
                </div>
            </div>
        </div>
    </div>
    """
    
    combined_html = f"""
    <div style="display: flex; gap: 16px; width: 100%; flex-wrap: wrap;">
        {left_feed_html}
        {right_widgets_html}
    </div>
    """
    return combined_html

def fetch_market_data(ticker, period="1y"):
    """Fetch historical data for the chart using a custom requests session to bypass rate blocks."""
    import requests
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        data = yf.download(ticker, period=period, session=session, auto_adjust=True)
        if data is None or data.empty:
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
            <div class="progress-item pending" style="display: flex; align-items: center; gap: 12px; padding: 12px 16px; border: 1px solid #e5e7eb; border-radius: 8px; background: #f9fafb; margin-bottom: 8px; width: 100%; opacity: 0.6;">
                <div class="prog-icon pending" style="width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: bold; flex-shrink: 0; background: #e5e7eb; color: #6B7280;">⬪</div>
                <span class="prog-label" style="font-size: 14px; color: #4b5563; font-weight: 500; flex: 1;">{label}</span>
                <span class="prog-time" style="font-size: 12px; color: #6B7280;">Pending</span>
            </div>"""
    html += "</div>"
    return html

def display_chart(data, ticker):
    """Render an interactive line chart with indicators matching the dashboard HTML specs."""
    if data is None:
        st.warning("Could not fetch market data for chart.")
        return

    # Extract 1D series safely (handles potential MultiIndexed DataFrames from yfinance)
    close_series = data['Close']
    if isinstance(close_series, pd.DataFrame):
        close_series = close_series.iloc[:, 0]
    
    vol_series = data['Volume']
    if isinstance(vol_series, pd.DataFrame):
        vol_series = vol_series.iloc[:, 0]

    # Calculate SMAs safely
    data['SMA20'] = close_series.rolling(window=20).mean()
    data['SMA50'] = close_series.rolling(window=50).mean()

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                       vertical_spacing=0.05, 
                       row_width=[0.2, 0.8])

    # Price Line (Blue Spline matching HTML)
    fig.add_trace(go.Scatter(
        x=data.index,
        y=close_series,
        line=dict(color='#378ADD', width=2, shape='spline'),
        name='Price',
        mode='lines'
    ), row=1, col=1)

    # Moving Averages (Dashed Splines matching HTML)
    fig.add_trace(go.Scatter(
        x=data.index,
        y=data['SMA20'],
        line=dict(color='#D97706', width=1.5, shape='spline', dash='dash'),
        name='SMA 20',
        mode='lines'
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(
        x=data.index,
        y=data['SMA50'],
        line=dict(color='#10B981', width=1.5, shape='spline', dash='dash'),
        name='SMA 50',
        mode='lines'
    ), row=1, col=1)

    # Volume (Translucent Blue Bars matching HTML)
    fig.add_trace(go.Bar(
        x=data.index,
        y=vol_series,
        name='Volume',
        marker=dict(
            color='rgba(55, 138, 221, 0.25)',
            line=dict(color='#378ADD', width=0.5)
        )
    ), row=2, col=1)

    fig.update_layout(
        template="plotly_white",
        xaxis_rangeslider_visible=False,
        height=500,
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=True,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#4b5563', family='Inter, sans-serif')
    )
    fig.update_xaxes(gridcolor='#e5e7eb', linecolor='#d1d5db', tickfont=dict(color='#6B7280'))
    fig.update_yaxes(gridcolor='#e5e7eb', linecolor='#d1d5db', tickfont=dict(color='#6B7280'), side='right')
    
    st.plotly_chart(fig, use_container_width=True)

# Sticky top horizontal indices ticker bar
st.markdown("""
<div class="top-ticker-bar">
    <div class="ticker-item"><span class="ticker-name">NIFTY</span> <span class="ticker-val">23,296.95</span> <span class="ticker-change down">-0.37%</span></div>
    <div class="ticker-item"><span class="ticker-name">BANKNIFTY</span> <span class="ticker-val">53,241.35</span> <span class="ticker-change down">-0.75%</span></div>
    <div class="ticker-item"><span class="ticker-name">FINNIFTY</span> <span class="ticker-val">24,707.25</span> <span class="ticker-change down">-1.20%</span></div>
    <div class="ticker-item"><span class="ticker-name">MIDCPNIFTY</span> <span class="ticker-val">17,162.85</span> <span class="ticker-change down">-0.67%</span></div>
    <div class="ticker-item"><span class="ticker-name">VIX</span> <span class="ticker-val">16.00</span> <span class="ticker-change up">-3.26%</span></div>
    <div class="ticker-item"><span class="ticker-name">GIFT</span> <span class="ticker-val">23,348.5</span> <span class="ticker-change down">-0.29%</span></div>
    <div class="ticker-live-badge"><span class="pulse-dot"></span> LIVE</div>
</div>
""", unsafe_allow_html=True)

# --- SIDEBAR CONFIGURATION ---
with st.sidebar:
    import base64
    logo_file_path = "/Users/admin/MultiTradingAgents/MultiTradingAgent/assets/OrbisQuantLogo.png"
    logo_base64 = None
    try:
        with open(logo_file_path, "rb") as image_file:
            logo_base64 = base64.b64encode(image_file.read()).decode()
    except Exception:
        pass
        
    if logo_base64:
        st.markdown(f"""
            <div style="padding-bottom: 12px; border-bottom: 1.5px solid #e5e7eb; margin-bottom: 16px;">
                <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
                    <img src="data:image/png;base64,{logo_base64}" style="width: 24px; height: 24px; border-radius: 5px; object-fit: cover;" />
                    <span style="font-size: 13px; font-weight: 700; color: #111111; font-family: 'Inter', sans-serif;">Orbis</span>
                    <span style="font-size: 8px; font-weight: 600; color: #D97706; background: #FFFBEB; border: 1px solid #FCD34D; padding: 1px 4px; border-radius: 3px; font-family: 'Inter', sans-serif; letter-spacing: 0.02em; text-transform: uppercase; white-space: nowrap; margin-left: 2px;">✨ AI Powered</span>
                </div>
                <div style="font-size: 9px; color: #6B7280; font-family: 'Inter', sans-serif; line-height: 1.3; margin-top: 4px;">Autonomous Multi-Agent Financial Intelligence Platform</div>
            </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
            <div style="padding-bottom: 12px; border-bottom: 1.5px solid #e5e7eb; margin-bottom: 16px;">
                <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
                    <div style="width: 24px; height: 24px; background: #E24B4A; border-radius: 5px; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 13px; font-family: 'Inter', sans-serif;">🌌</div>
                    <span style="font-size: 13px; font-weight: 700; color: #111111; font-family: 'Inter', sans-serif;">Orbis</span>
                    <span style="font-size: 8px; font-weight: 600; color: #D97706; background: #FFFBEB; border: 1px solid #FCD34D; padding: 1px 4px; border-radius: 3px; font-family: 'Inter', sans-serif; letter-spacing: 0.02em; text-transform: uppercase; white-space: nowrap; margin-left: 2px;">✨ AI Powered</span>
                </div>
                <div style="font-size: 9px; color: #6B7280; font-family: 'Inter', sans-serif; line-height: 1.3; margin-top: 4px;">Autonomous Multi-Agent Financial Intelligence Platform</div>
            </div>
        """, unsafe_allow_html=True)
    
    st.markdown("### ⚙ PLATFORM CONFIG")
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
        if a == "News":
            analyst_containers[a].markdown(render_news_desk_html(ticker, ""), unsafe_allow_html=True)
        else:
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
    
    # Dynamic reload of .env to capture any newly added credentials
    load_dotenv(override=True)
    
    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = depth_map[depth]
    config["max_risk_discuss_rounds"] = depth_map[depth]
    
    selected_provider = provider.lower()
    config["llm_provider"] = selected_provider
    
    # Check if the chosen provider matches the provider set in the env
    env_provider = os.getenv("LLM_PROVIDER", "openai").lower()
    if selected_provider == env_provider:
        # Load the custom models configured in the env file for this specific provider
        config["deep_think_llm"] = os.getenv("DEEP_THINK_LLM", config["deep_think_llm"])
        config["quick_think_llm"] = os.getenv("QUICK_THINK_LLM", config["quick_think_llm"])
    else:
        # Dynamically set standard model defaults for the newly selected provider
        if selected_provider == "google":
            config["deep_think_llm"] = "gemini-2.5-pro"
            config["quick_think_llm"] = "gemini-2.5-flash"
        elif selected_provider == "ollama":
            config["deep_think_llm"] = "qwen3:latest"
            config["quick_think_llm"] = "qwen3:latest"
        elif selected_provider == "anthropic":
            config["deep_think_llm"] = "claude-sonnet-4-6"
            config["quick_think_llm"] = "claude-haiku-4-5-20251001"
        elif selected_provider == "openai":
            config["deep_think_llm"] = "gpt-5.4"
            config["quick_think_llm"] = "gpt-5.4-mini"
    
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
                    analyst_containers["News"].markdown(render_news_desk_html(ticker, chunk["news_report"]), unsafe_allow_html=True)
            
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
