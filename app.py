"""
app.py — AlgoTrader Pro: Live Algorithmic Trading Dashboard
============================================================
Run with:  streamlit run app.py

Works in DEMO MODE out of the box (no API keys needed).
Add Alpaca paper-trading credentials in .env for live paper execution.
"""
from __future__ import annotations

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from typing import Dict, List

from config import Config
from data.market_data import fetch_historical, fetch_quotes_bulk, fetch_quote
from strategies.mean_reversion import MeanReversionStrategy
from strategies.momentum import MomentumStrategy
from trading.alpaca_client import AlpacaClient
from trading.risk_manager import RiskManager
from trading.order_manager import OrderManager
from utils.helpers import fmt_currency, fmt_pct, confidence_bar

# ══════════════════════════════════════════════════════════════════════════════
# PAGE SETUP
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="AlgoTrader Pro",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Syne:wght@400;600;700;800&display=swap');

/* Base */
html, body, [class*="css"] { font-family: 'Syne', sans-serif; }
.stApp { background: #060b14; }
[data-testid="stSidebar"] { background: #08111d !important; border-right: 1px solid #1a2e44; }
[data-testid="stSidebar"] * { color: #cdd6f4 !important; }

/* Metric cards */
[data-testid="stMetric"] {
    background: #0d1b2a;
    border: 1px solid #1a2e44;
    border-radius: 10px;
    padding: 16px 20px;
}
[data-testid="stMetricValue"]  { font-size: 1.7rem !important; font-weight: 700; color: #cdd6f4 !important; }
[data-testid="stMetricLabel"]  { font-size: .75rem !important; color: #6b7fa3 !important; text-transform: uppercase; letter-spacing: .08em; }
[data-testid="stMetricDelta"]  { font-size: .85rem !important; font-family: 'JetBrains Mono', monospace; }

/* Tables */
[data-testid="stDataFrame"] { background: #0d1b2a !important; border: 1px solid #1a2e44; border-radius: 8px; }

/* Tabs */
[data-baseweb="tab-list"] { background: #0d1b2a; border-radius: 8px; padding: 4px; gap: 4px; }
[data-baseweb="tab"]      { background: transparent !important; border-radius: 6px; color: #6b7fa3 !important; }
[aria-selected="true"][data-baseweb="tab"] { background: #1a2e44 !important; color: #00d4ff !important; }

/* Buttons */
.stButton > button {
    background: linear-gradient(135deg, #00d4ff22, #3a7bd522);
    border: 1px solid #00d4ff55;
    color: #00d4ff;
    border-radius: 8px;
    font-family: 'Syne', sans-serif;
    font-weight: 600;
    transition: all .2s;
}
.stButton > button:hover { background: #00d4ff33; border-color: #00d4ff; }

/* Signal badges */
.badge-buy  { background:#00e5a022; color:#00e5a0; border:1px solid #00e5a055; padding:3px 10px; border-radius:20px; font-weight:700; font-size:.8rem; }
.badge-sell { background:#ff3d5a22; color:#ff3d5a; border:1px solid #ff3d5a55; padding:3px 10px; border-radius:20px; font-weight:700; font-size:.8rem; }
.badge-hold { background:#ffd16622; color:#ffd166; border:1px solid #ffd16655; padding:3px 10px; border-radius:20px; font-weight:700; font-size:.8rem; }

/* Section headers */
.section-header {
    color: #6b7fa3;
    font-size: .7rem;
    text-transform: uppercase;
    letter-spacing: .12em;
    font-weight: 600;
    margin: 1.5rem 0 .5rem 0;
    border-bottom: 1px solid #1a2e44;
    padding-bottom: 4px;
}
/* Status pill */
.status-live { color: #00e5a0; background: #00e5a015; border: 1px solid #00e5a040; padding: 2px 10px; border-radius: 20px; font-size:.75rem; font-weight:600; }
.status-demo { color: #ffd166; background: #ffd16615; border: 1px solid #ffd16640; padding: 2px 10px; border-radius: 20px; font-size:.75rem; font-weight:600; }

/* Monospace numbers */
.mono { font-family: 'JetBrains Mono', monospace; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE INITIALISATION
# ══════════════════════════════════════════════════════════════════════════════

def init_state() -> None:
    defaults = {
        "demo_portfolio": {
            "cash":      Config.INITIAL_CAPITAL,
            "positions": {},
            "trade_log": [],
        },
        "watchlist":     list(Config.DEFAULT_WATCHLIST),
        "strategy_name": "Mean Reversion (BB)",
        "auto_trade":    False,
        "last_refresh":  datetime.now(),
        "backtest_results": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ══════════════════════════════════════════════════════════════════════════════
# COMPONENT INITIALISATION  (cached for the lifetime of the session)
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource
def init_components(api_key: str, secret_key: str, base_url: str):
    alpaca = AlpacaClient(api_key, secret_key, base_url)
    risk   = RiskManager()
    return alpaca, risk


STRATEGIES = {
    "Mean Reversion (BB)": MeanReversionStrategy(),
    "Momentum (RSI+MACD)": MomentumStrategy(),
}


# ══════════════════════════════════════════════════════════════════════════════
# CHART BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_chart(
    df: pd.DataFrame,
    symbol: str,
    strategy_name: str,
    trade_log: List[Dict],
) -> go.Figure:
    """Build a 3-row Plotly chart: candlestick+overlays | volume | oscillator."""

    is_mr = "Mean Reversion" in strategy_name

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.60, 0.18, 0.22],
        vertical_spacing=0.02,
        subplot_titles=("", "", "RSI" if is_mr else "MACD"),
    )

    # ── Row 1: Candlestick ────────────────────────────────────────────────────
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        name=symbol,
        increasing=dict(line=dict(color="#00e5a0"), fillcolor="rgba(0,229,160,0.2)"),
        decreasing=dict(line=dict(color="#ff3d5a"), fillcolor="rgba(255,61,90,0.2)"),
        showlegend=False,
    ), row=1, col=1)

    # Bollinger Bands (mean reversion mode)
    if is_mr and "BB_upper" in df.columns:
        for col, name, dash in [
            ("BB_upper", "Upper BB", "dash"),
            ("BB_mid",   "Mid BB",   "dot"),
            ("BB_lower", "Lower BB", "dash"),
        ]:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[col], name=name,
                line=dict(color="#3a7bd5", width=1, dash=dash),
                opacity=0.75, showlegend=True,
            ), row=1, col=1)

        # Band fill
        fig.add_trace(go.Scatter(
            x=list(df.index) + list(df.index[::-1]),
            y=list(df["BB_upper"]) + list(df["BB_lower"][::-1]),
            fill="toself",
            fillcolor="rgba(58,123,213,0.06)",
            line=dict(color="rgba(0,0,0,0)"),
            name="BB Band",
            showlegend=False,
        ), row=1, col=1)

    # EMAs (momentum mode)
    if not is_mr and "EMA_20" in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["EMA_20"], name="EMA 20",
            line=dict(color="#ffd166", width=1.2), showlegend=True,
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["EMA_50"], name="EMA 50",
            line=dict(color="#ff6b6b", width=1.2), showlegend=True,
        ), row=1, col=1)

    # Trade markers from log
    buy_dates  = [t["timestamp"][:10] for t in trade_log if t["side"] == "BUY"]
    sell_dates = [t["timestamp"][:10] for t in trade_log if t["side"] == "SELL"]
    buy_prices  = [t["price"] for t in trade_log if t["side"] == "BUY"]
    sell_prices = [t["price"] for t in trade_log if t["side"] == "SELL"]

    if buy_dates:
        fig.add_trace(go.Scatter(
            x=buy_dates, y=buy_prices,
            mode="markers", name="BUY",
            marker=dict(symbol="triangle-up", size=10, color="#00e5a0"),
        ), row=1, col=1)
    if sell_dates:
        fig.add_trace(go.Scatter(
            x=sell_dates, y=sell_prices,
            mode="markers", name="SELL",
            marker=dict(symbol="triangle-down", size=10, color="#ff3d5a"),
        ), row=1, col=1)

    # ── Row 2: Volume ─────────────────────────────────────────────────────────
    vol_colors = [
        "rgba(0,229,160,0.4)" if c >= o else "rgba(255,61,90,0.4)"
        for c, o in zip(df["Close"], df["Open"])
    ]
    fig.add_trace(go.Bar(
        x=df.index, y=df["Volume"],
        name="Volume", marker_color=vol_colors,
        showlegend=False,
    ), row=2, col=1)
    if "Vol_SMA" in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["Vol_SMA"],
            name="Vol SMA", line=dict(color="#6b7fa3", width=1),
            showlegend=False,
        ), row=2, col=1)

    # ── Row 3: RSI or MACD ───────────────────────────────────────────────────
    if is_mr and "RSI" in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["RSI"],
            name="RSI", line=dict(color="#00d4ff", width=1.5),
            showlegend=False,
        ), row=3, col=1)
        for level, color in [(70, "#ff3d5a"), (30, "#00e5a0"), (50, "#6b7fa3")]:
            fig.add_hline(y=level, line_dash="dash", line_color=color,
                          opacity=0.4, row=3, col=1)
        fig.update_yaxes(range=[0, 100], row=3, col=1)

    elif "MACD" in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["MACD"],
            name="MACD", line=dict(color="#00d4ff", width=1.5),
            showlegend=False,
        ), row=3, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["MACD_signal"],
            name="Signal", line=dict(color="#ffd166", width=1),
            showlegend=False,
        ), row=3, col=1)
        hist_colors = [
            "#00e5a0" if h >= 0 else "#ff3d5a"
            for h in df["MACD_hist"]
        ]
        fig.add_trace(go.Bar(
            x=df.index, y=df["MACD_hist"],
            name="Histogram", marker_color=hist_colors, opacity=0.6,
            showlegend=False,
        ), row=3, col=1)
        fig.add_hline(y=0, line_color="#6b7fa3", opacity=0.3, row=3, col=1)

    # ── Layout ────────────────────────────────────────────────────────────────
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#060b14",
        plot_bgcolor="#060b14",
        height=Config.CHART_HEIGHT,
        margin=dict(l=0, r=0, t=8, b=0),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.01,
            font=dict(size=11, color="#6b7fa3"),
        ),
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor="#1a2e44", showgrid=True)
    fig.update_yaxes(gridcolor="#1a2e44", showgrid=True)

    return fig


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

def render_sidebar(alpaca: AlpacaClient) -> tuple:
    with st.sidebar:
        # Logo / title
        st.markdown("""
        <div style='text-align:center;padding:16px 0 8px 0'>
            <span style='font-size:2rem'>📈</span><br>
            <span style='font-family:Syne;font-weight:800;font-size:1.3rem;
                         background:linear-gradient(90deg,#00d4ff,#3a7bd5);
                         -webkit-background-clip:text;-webkit-text-fill-color:transparent'>
                AlgoTrader Pro
            </span><br>
            <span style='font-size:.7rem;color:#6b7fa3'>Algorithmic Trading Dashboard</span>
        </div>
        """, unsafe_allow_html=True)

        # Connection status
        if alpaca.connected:
            st.markdown('<p style="text-align:center"><span class="status-live">● LIVE (Paper)</span></p>',
                        unsafe_allow_html=True)
        else:
            st.markdown('<p style="text-align:center"><span class="status-demo">● DEMO MODE</span></p>',
                        unsafe_allow_html=True)
            with st.expander("🔑 Connect Alpaca", expanded=False):
                st.info(
                    "Add credentials to `.env` (see `.env.example`) "
                    "and restart the app for live paper trading.\n\n"
                    "**Free signup:** alpaca.markets"
                )

        st.markdown("---")

        # ── Strategy ──────────────────────────────────────────────────────────
        st.markdown('<p class="section-header">Strategy</p>', unsafe_allow_html=True)
        strategy_name = st.selectbox(
            "Active Strategy",
            list(STRATEGIES.keys()),
            index=list(STRATEGIES.keys()).index(st.session_state.strategy_name),
            label_visibility="collapsed",
        )
        st.session_state.strategy_name = strategy_name

        # ── Symbol ────────────────────────────────────────────────────────────
        st.markdown('<p class="section-header">Symbol</p>', unsafe_allow_html=True)
        selected_symbol = st.selectbox(
            "Watchlist",
            st.session_state.watchlist,
            label_visibility="collapsed",
        )

        # Add to watchlist
        new_sym = st.text_input("Add symbol", placeholder="e.g. NFLX", max_chars=6)
        if st.button("➕ Add") and new_sym:
            sym = new_sym.upper().strip()
            if sym not in st.session_state.watchlist:
                st.session_state.watchlist.append(sym)
                st.rerun()

        st.markdown('<p class="section-header">Auto Trading</p>', unsafe_allow_html=True)
        auto_trade = st.toggle(
            "Execute signals automatically",
            value=st.session_state.auto_trade,
            help="When ON, BUY/SELL signals are executed automatically each refresh.",
        )
        st.session_state.auto_trade = auto_trade

        if auto_trade:
            st.warning("⚡ Auto-trade ON — signals will execute orders!", icon="⚠️")

        # ── Risk params (read-only preview) ───────────────────────────────────
        st.markdown('<p class="section-header">Risk Parameters</p>', unsafe_allow_html=True)
        st.markdown(f"""
        <div style='font-size:.8rem;color:#6b7fa3;line-height:1.9'>
        🛑 Stop Loss &nbsp;&nbsp;&nbsp;&nbsp; <span style='color:#cdd6f4;font-family:JetBrains Mono'>{Config.STOP_LOSS_PCT:.0%}</span><br>
        🎯 Take Profit &nbsp;&nbsp; <span style='color:#cdd6f4;font-family:JetBrains Mono'>{Config.TAKE_PROFIT_PCT:.0%}</span><br>
        📦 Max Position &nbsp; <span style='color:#cdd6f4;font-family:JetBrains Mono'>{Config.MAX_POSITION_PCT:.0%}</span><br>
        🔢 Max Positions &nbsp; <span style='color:#cdd6f4;font-family:JetBrains Mono'>{Config.MAX_OPEN_POSITIONS}</span><br>
        💰 Risk / Trade &nbsp;&nbsp; <span style='color:#cdd6f4;font-family:JetBrains Mono'>{Config.RISK_PER_TRADE_PCT:.0%}</span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")

        # Manual trade panel
        st.markdown('<p class="section-header">Manual Order</p>', unsafe_allow_html=True)
        mo_sym   = st.text_input("Symbol", value=selected_symbol, key="mo_sym")
        mo_qty   = st.number_input("Shares", min_value=1, value=1, step=1, key="mo_qty")
        mo_side  = st.radio("Side", ["BUY", "SELL"], horizontal=True, key="mo_side")

        if st.button("🚀 Place Order"):
            q = fetch_quote(mo_sym.upper())
            if q:
                st.session_state["_manual_order"] = {
                    "symbol": mo_sym.upper(),
                    "qty":    mo_qty,
                    "side":   mo_side.lower(),
                    "price":  q["price"],
                }
            else:
                st.error("Could not fetch price for that symbol.")

        # Refresh
        st.markdown("---")
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.session_state.last_refresh = datetime.now()
            st.rerun()

        ts = st.session_state.last_refresh.strftime("%H:%M:%S")
        st.markdown(
            f'<p style="text-align:center;font-size:.7rem;color:#6b7fa3">Last refresh: {ts}</p>',
            unsafe_allow_html=True,
        )

    return strategy_name, selected_symbol, auto_trade


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

def render_dashboard(
    alpaca: AlpacaClient,
    order_manager: OrderManager,
    risk: RiskManager,
    selected_symbol: str,
    strategy_name: str,
    auto_trade: bool,
) -> None:
    strategy = STRATEGIES[strategy_name]

    # ── Portfolio Metrics ─────────────────────────────────────────────────────
    if alpaca.connected:
        acc       = alpaca.get_account() or {}
        pv        = acc.get("portfolio_value", Config.INITIAL_CAPITAL)
        cash      = acc.get("cash", pv)
        pnl       = acc.get("pnl", 0.0)
        positions = alpaca.get_positions()
    else:
        cash      = st.session_state.demo_portfolio.get("cash", Config.INITIAL_CAPITAL)
        pos_val   = sum(
            p["price"] * p["qty"]
            for p in st.session_state.demo_portfolio.get("positions", {}).values()
        )
        pv        = cash + pos_val
        pnl       = pv - Config.INITIAL_CAPITAL
        positions = order_manager.get_demo_positions()

    pnl_pct    = pnl / Config.INITIAL_CAPITAL * 100
    n_pos      = len(positions)
    total_ret  = ((pv / Config.INITIAL_CAPITAL) - 1) * 100

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Portfolio Value", f"${pv:,.2f}",
                  f"{fmt_pct(total_ret)} total return")
    with c2:
        st.metric("Session P&L", f"${pnl:+,.2f}",
                  f"{fmt_pct(pnl_pct)}")
    with c3:
        st.metric("Cash Available", f"${cash:,.2f}",
                  f"{cash/pv:.0%} of portfolio")
    with c4:
        st.metric("Open Positions", str(n_pos),
                  f"of {Config.MAX_OPEN_POSITIONS} max")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Watchlist Quote Bar ───────────────────────────────────────────────────
    watchlist = st.session_state.watchlist[:8]
    quotes_df = fetch_quotes_bulk(watchlist)

    if not quotes_df.empty:
        cols = st.columns(len(watchlist))
        for i, row in quotes_df.iterrows():
            color = Config.C_GREEN if row["change_pct"] >= 0 else Config.C_RED
            sign  = "▲" if row["change_pct"] >= 0 else "▼"
            with cols[i]:
                st.markdown(f"""
                <div style='background:#0d1b2a;border:1px solid #1a2e44;border-radius:8px;
                            padding:8px 10px;text-align:center'>
                    <div style='font-size:.75rem;color:#6b7fa3;font-weight:600'>{row["symbol"]}</div>
                    <div style='font-size:1rem;font-weight:700;color:#cdd6f4'>${row["price"]:.2f}</div>
                    <div style='font-size:.7rem;color:{color}'>{sign} {abs(row["change_pct"]):.2f}%</div>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Chart + Signal ────────────────────────────────────────────────────────
    df = fetch_historical(selected_symbol, Config.DATA_LOOKBACK)

    col_chart, col_signal = st.columns([3, 1])

    with col_chart:
        st.markdown(f'<p class="section-header">📊 {selected_symbol} — {strategy_name}</p>',
                    unsafe_allow_html=True)
        if df.empty:
            st.error(f"No data available for {selected_symbol}")
        else:
            fig = build_chart(df, selected_symbol, strategy_name,
                              st.session_state.demo_portfolio.get("trade_log", []))
            st.plotly_chart(fig, use_container_width=True)

    with col_signal:
        st.markdown('<p class="section-header">🎯 Current Signal</p>',
                    unsafe_allow_html=True)
        if not df.empty:
            sig = strategy.generate_signal(df, selected_symbol)

            badge_cls = {"BUY": "badge-buy", "SELL": "badge-sell", "HOLD": "badge-hold"}[sig.signal]
            st.markdown(
                f'<div style="text-align:center;margin:12px 0">'
                f'<span class="{badge_cls}" style="font-size:1.4rem;padding:8px 28px">'
                f'{sig.signal}</span></div>',
                unsafe_allow_html=True,
            )
            st.markdown(f"""
            <div style='background:#0d1b2a;border:1px solid #1a2e44;border-radius:8px;padding:14px;font-size:.82rem'>
                <div style='color:#6b7fa3;margin-bottom:4px'>Price</div>
                <div style='color:#cdd6f4;font-family:JetBrains Mono;font-size:1.1rem'>${sig.price:.2f}</div>
                <div style='color:#6b7fa3;margin:8px 0 4px 0'>Confidence</div>
                <div style='color:#cdd6f4;font-family:JetBrains Mono'>{confidence_bar(sig.confidence)}</div>
                <div style='color:#6b7fa3;margin:8px 0 4px 0'>Reason</div>
                <div style='color:#cdd6f4'>{sig.reason}</div>
            </div>
            """, unsafe_allow_html=True)

            # Risk details for BUY signals
            if sig.signal == "BUY" and "ATR" in df.columns:
                atr = float(df["ATR"].iloc[-1])
                rs  = risk.position_summary(pv, sig.price, atr)
                st.markdown('<p class="section-header">📐 Position Sizing</p>',
                            unsafe_allow_html=True)
                st.markdown(f"""
                <div style='background:#0d1b2a;border:1px solid #1a2e44;border-radius:8px;
                            padding:14px;font-size:.8rem;color:#6b7fa3;line-height:2'>
                Shares &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
                <span style='color:#cdd6f4;font-family:JetBrains Mono'>{rs['shares']}</span><br>
                Cost &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
                <span style='color:#cdd6f4;font-family:JetBrains Mono'>${rs['cost']:,.2f}</span><br>
                Stop Loss &nbsp;&nbsp;
                <span style='color:#ff3d5a;font-family:JetBrains Mono'>${rs['stop_loss']:.2f}</span><br>
                Take Profit
                <span style='color:#00e5a0;font-family:JetBrains Mono'>&nbsp;${rs['take_profit']:.2f}</span><br>
                Max Loss &nbsp;&nbsp;&nbsp;
                <span style='color:#ffd166;font-family:JetBrains Mono'>${rs['max_loss']:,.2f}</span><br>
                R:R Ratio &nbsp;&nbsp;
                <span style='color:#cdd6f4;font-family:JetBrains Mono'>1:{rs['risk_reward']:.1f}</span>
                </div>
                """, unsafe_allow_html=True)

            # Auto-trade execution
            if auto_trade and sig.signal in ("BUY", "SELL"):
                latest = df.iloc[-1].to_dict()
                result = order_manager.execute(sig, latest)
                if result:
                    action = "✅ BUY" if sig.signal == "BUY" else "🔴 SELL"
                    st.success(f"{action} executed: {result.get('qty')} shares @ ${sig.price:.2f}")

    # ── Manual order execution ────────────────────────────────────────────────
    if "_manual_order" in st.session_state:
        mo = st.session_state.pop("_manual_order")
        sig_m = from_manual(mo)
        result = order_manager.manual_order(
            mo["symbol"], mo["qty"], mo["side"], mo["price"]
        )
        if result:
            st.success(
                f"✅ Manual {mo['side'].upper()} {mo['qty']} {mo['symbol']} "
                f"@ ${mo['price']:.2f}"
            )

    st.markdown("---")

    # ── All Signals Table ─────────────────────────────────────────────────────
    st.markdown('<p class="section-header">📡 Signals — All Watchlist</p>',
                unsafe_allow_html=True)
    signal_rows = []
    for sym in st.session_state.watchlist:
        sym_df = fetch_historical(sym, Config.DATA_LOOKBACK)
        if not sym_df.empty:
            s = strategy.generate_signal(sym_df, sym)
            rsi_val = f"{sym_df['RSI'].iloc[-1]:.1f}" if "RSI" in sym_df else "—"
            signal_rows.append({
                "Symbol":     sym,
                "Price":      f"${s.price:.2f}",
                "Signal":     s.signal,
                "Confidence": f"{s.confidence:.0%}",
                "RSI":        rsi_val,
                "Reason":     s.reason[:70] + ("…" if len(s.reason) > 70 else ""),
            })

    if signal_rows:
        sig_df = pd.DataFrame(signal_rows)

        def highlight_signal(row):
            colors = {"BUY": "rgba(0,229,160,0.08)", "SELL": "rgba(255,61,90,0.08)", "HOLD": "rgba(255,209,102,0.06)"}
            c = colors.get(row["Signal"], "")
            return [f"background-color:{c}"] * len(row)

        styled = sig_df.style.apply(highlight_signal, axis=1)
        st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Positions & Trade Log ─────────────────────────────────────────────────
    col_pos, col_log = st.columns(2)

    with col_pos:
        st.markdown('<p class="section-header">📂 Open Positions</p>',
                    unsafe_allow_html=True)
        if positions:
            pos_df = pd.DataFrame(positions)
            # Refresh demo prices
            if not alpaca.connected and not pos_df.empty:
                for sym in pos_df["symbol"].tolist():
                    q = fetch_quote(sym)
                    if q:
                        order_manager.update_demo_prices({sym: q["price"]})
                positions = order_manager.get_demo_positions()
                pos_df = pd.DataFrame(positions)

            def colour_pnl(val):
                try:
                    v = float(str(val).replace("$", "").replace(",", "").replace("+", ""))
                    color = "#00e5a0" if v > 0 else "#ff3d5a"
                    return f"color: {color}"
                except Exception:
                    return ""

            if not pos_df.empty:
                pos_df["pnl"] = pos_df["pnl"].apply(lambda x: f"${x:+,.2f}")
                pos_df["pnl_pct"] = pos_df["pnl_pct"].apply(lambda x: f"{x:+.2f}%")
                st.dataframe(
                    pos_df.style.applymap(colour_pnl, subset=["pnl", "pnl_pct"]),
                    use_container_width=True, hide_index=True,
                )
        else:
            st.info("No open positions.")

    with col_log:
        st.markdown('<p class="section-header">📝 Trade Log</p>',
                    unsafe_allow_html=True)
        log = order_manager.get_trade_log()
        if log:
            log_df = pd.DataFrame(log[:20])   # last 20
            st.dataframe(log_df, use_container_width=True, hide_index=True)
        else:
            st.info("No trades executed yet.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — BACKTESTING
# ══════════════════════════════════════════════════════════════════════════════

def render_backtest(selected_symbol: str, strategy_name: str) -> None:
    strategy = STRATEGIES[strategy_name]

    st.markdown(f"### Backtest: **{strategy_name}** on **{selected_symbol}**")
    st.caption("Walk-forward simulation on historical data — no look-ahead bias.")

    col_settings, col_run = st.columns([2, 1])
    with col_settings:
        period     = st.selectbox("Data Period", ["3mo", "6mo", "1y", "2y"], index=1)
        init_cap   = st.number_input("Initial Capital ($)", value=100_000, step=10_000)
        sl_pct     = st.slider("Stop Loss %",   1, 10, int(Config.STOP_LOSS_PCT * 100)) / 100
        tp_pct     = st.slider("Take Profit %", 1, 20, int(Config.TAKE_PROFIT_PCT * 100)) / 100
    with col_run:
        st.markdown("<br><br>", unsafe_allow_html=True)
        run_bt = st.button("▶ Run Backtest", use_container_width=True)

    if run_bt:
        with st.spinner(f"Running backtest on {period} of {selected_symbol} data…"):
            df = fetch_historical(selected_symbol, period)
            if df.empty or len(df) < 70:
                st.error("Not enough data. Try a longer period or different symbol.")
                return

            results = strategy.backtest(
                df, selected_symbol, float(init_cap), sl_pct, tp_pct
            )
            st.session_state.backtest_results = results

    # Display results
    if st.session_state.backtest_results:
        r = st.session_state.backtest_results
        st.markdown("---")

        # KPI row
        mc1, mc2, mc3, mc4, mc5 = st.columns(5)
        with mc1:
            delta_color = "normal" if r["total_return"] >= 0 else "inverse"
            st.metric("Total Return", f"{r['total_return']:+.2f}%",
                      f"${r['final'] - r['initial']:+,.0f}")
        with mc2:
            st.metric("Sharpe Ratio", f"{r['sharpe']:.2f}",
                      "annualised, rf=0")
        with mc3:
            st.metric("Max Drawdown", f"{r['max_drawdown']:.2f}%")
        with mc4:
            st.metric("Win Rate", f"{r['win_rate']:.1f}%",
                      f"{r['n_trades']} trades")
        with mc5:
            st.metric("Avg Trade P&L", f"${r['avg_pnl']:+,.2f}")

        # Equity curve
        if r["equity_curve"]:
            eq_df = pd.DataFrame({
                "Equity":    r["equity_curve"],
                "Benchmark": [r["initial"]] * len(r["equity_curve"]),   # buy & hold approx
            }, index=r["equity_index"][:len(r["equity_curve"])])

            fig_eq = go.Figure()
            fig_eq.add_trace(go.Scatter(
                x=eq_df.index, y=eq_df["Equity"],
                name="Strategy", fill="tozeroy",
                line=dict(color="#00d4ff", width=2),
                fillcolor="rgba(0,212,255,0.08)",
            ))
            fig_eq.add_trace(go.Scatter(
                x=eq_df.index, y=eq_df["Benchmark"],
                name="Initial Capital",
                line=dict(color="#6b7fa3", width=1, dash="dash"),
            ))
            fig_eq.update_layout(
                template="plotly_dark",
                paper_bgcolor="#060b14", plot_bgcolor="#060b14",
                height=320, margin=dict(l=0, r=0, t=8, b=0),
                legend=dict(orientation="h"),
                yaxis=dict(tickprefix="$", gridcolor="#1a2e44"),
                xaxis=dict(gridcolor="#1a2e44"),
            )
            st.markdown('<p class="section-header">Equity Curve</p>',
                        unsafe_allow_html=True)
            st.plotly_chart(fig_eq, use_container_width=True)

        # Trade history table
        if r["trades"]:
            st.markdown('<p class="section-header">Trade History</p>',
                        unsafe_allow_html=True)
            trades_df = pd.DataFrame(r["trades"])
            trades_df["date"]  = pd.to_datetime(trades_df["date"]).dt.strftime("%Y-%m-%d")
            trades_df["price"] = trades_df["price"].apply(lambda x: f"${x:.2f}")
            trades_df["pnl"]   = trades_df["pnl"].apply(
                lambda x: f"${x:+,.2f}" if x is not None else "—"
            )

            def color_trade(row):
                if row["type"] == "BUY":
                    return ["background-color:rgba(0,229,160,0.06)"] * len(row)
                try:
                    pnl = float(row["pnl"].replace("$","").replace(",","").replace("+",""))
                    c = "rgba(0,229,160,0.06)" if pnl > 0 else "rgba(255,61,90,0.06)"
                    return [f"background-color:{c}"] * len(row)
                except Exception:
                    return [""] * len(row)

            st.dataframe(
                trades_df.style.apply(color_trade, axis=1),
                use_container_width=True, hide_index=True,
            )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — PORTFOLIO
# ══════════════════════════════════════════════════════════════════════════════

def render_portfolio(
    alpaca: AlpacaClient,
    order_manager: OrderManager,
) -> None:

    st.markdown("### Portfolio Overview")

    if alpaca.connected:
        acc       = alpaca.get_account() or {}
        positions = alpaca.get_positions()
        orders    = alpaca.get_orders(status="all", limit=25)
    else:
        acc = {
            "portfolio_value": (
                st.session_state.demo_portfolio.get("cash", Config.INITIAL_CAPITAL)
                + sum(
                    p["price"] * p["qty"]
                    for p in st.session_state.demo_portfolio.get("positions", {}).values()
                )
            ),
            "cash": st.session_state.demo_portfolio.get("cash", Config.INITIAL_CAPITAL),
        }
        positions = order_manager.get_demo_positions()
        orders    = order_manager.get_trade_log()[:25]

    pv   = acc.get("portfolio_value", Config.INITIAL_CAPITAL)
    cash = acc.get("cash", pv)

    # Allocation donut chart
    col_donut, col_stats = st.columns([1, 1])

    with col_donut:
        labels, values, colors = ["Cash"], [cash], ["#3a7bd5"]
        for p in positions:
            labels.append(p["symbol"])
            values.append(p.get("mkt_val", p.get("mkt_value", 0)))
            colors.append("#00d4ff")

        fig_donut = go.Figure(go.Pie(
            labels=labels, values=values,
            hole=0.65,
            marker=dict(colors=colors, line=dict(color="#060b14", width=2)),
            textinfo="label+percent",
            textfont=dict(color="#cdd6f4"),
        ))
        fig_donut.add_annotation(
            text=f"${pv:,.0f}", x=0.5, y=0.5,
            font=dict(size=16, color="#cdd6f4"), showarrow=False,
        )
        fig_donut.update_layout(
            template="plotly_dark",
            paper_bgcolor="#060b14",
            height=300,
            margin=dict(l=0, r=0, t=8, b=0),
            showlegend=True,
            legend=dict(font=dict(color="#6b7fa3", size=11)),
        )
        st.markdown('<p class="section-header">Portfolio Allocation</p>',
                    unsafe_allow_html=True)
        st.plotly_chart(fig_donut, use_container_width=True)

    with col_stats:
        total_pnl   = pv - Config.INITIAL_CAPITAL
        total_ret   = total_pnl / Config.INITIAL_CAPITAL * 100
        n_trades    = len(order_manager.get_trade_log())

        st.markdown('<p class="section-header">Account Summary</p>',
                    unsafe_allow_html=True)
        st.markdown(f"""
        <div style='background:#0d1b2a;border:1px solid #1a2e44;border-radius:10px;
                    padding:20px;font-size:.9rem;line-height:2.2'>
            <div style='display:flex;justify-content:space-between'>
                <span style='color:#6b7fa3'>Portfolio Value</span>
                <span style='color:#cdd6f4;font-family:JetBrains Mono'>${pv:,.2f}</span>
            </div>
            <div style='display:flex;justify-content:space-between'>
                <span style='color:#6b7fa3'>Cash Balance</span>
                <span style='color:#cdd6f4;font-family:JetBrains Mono'>${cash:,.2f}</span>
            </div>
            <div style='display:flex;justify-content:space-between'>
                <span style='color:#6b7fa3'>Total P&L</span>
                <span style='color:{"#00e5a0" if total_pnl>=0 else "#ff3d5a"};font-family:JetBrains Mono'>
                    ${total_pnl:+,.2f}
                </span>
            </div>
            <div style='display:flex;justify-content:space-between'>
                <span style='color:#6b7fa3'>Total Return</span>
                <span style='color:{"#00e5a0" if total_ret>=0 else "#ff3d5a"};font-family:JetBrains Mono'>
                    {total_ret:+.2f}%
                </span>
            </div>
            <div style='display:flex;justify-content:space-between'>
                <span style='color:#6b7fa3'>Initial Capital</span>
                <span style='color:#cdd6f4;font-family:JetBrains Mono'>${Config.INITIAL_CAPITAL:,.2f}</span>
            </div>
            <div style='display:flex;justify-content:space-between'>
                <span style='color:#6b7fa3'>Open Positions</span>
                <span style='color:#cdd6f4;font-family:JetBrains Mono'>{len(positions)}</span>
            </div>
            <div style='display:flex;justify-content:space-between'>
                <span style='color:#6b7fa3'>Total Trades</span>
                <span style='color:#cdd6f4;font-family:JetBrains Mono'>{n_trades}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Reset demo button
        if not alpaca.connected:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔁 Reset Demo Portfolio", use_container_width=True):
                st.session_state.demo_portfolio = {
                    "cash":      Config.INITIAL_CAPITAL,
                    "positions": {},
                    "trade_log": [],
                }
                st.success("Demo portfolio reset to $100,000.")
                st.rerun()

    # Positions detail
    if positions:
        st.markdown('<p class="section-header">Position Details</p>',
                    unsafe_allow_html=True)
        pos_df = pd.DataFrame(positions)
        st.dataframe(pos_df, use_container_width=True, hide_index=True)

    # Order / trade history
    st.markdown('<p class="section-header">Order History</p>', unsafe_allow_html=True)
    if orders:
        st.dataframe(pd.DataFrame(orders), use_container_width=True, hide_index=True)
    else:
        st.info("No order history.")


# ══════════════════════════════════════════════════════════════════════════════
# UTILITY
# ══════════════════════════════════════════════════════════════════════════════

def from_manual(mo: dict):
    """Create a dummy Signal object for manual order logging."""
    from strategies.base_strategy import Signal
    return Signal(
        symbol=mo["symbol"], signal="BUY" if mo["side"] == "buy" else "SELL",
        price=mo["price"], confidence=1.0,
        reason="Manual order via UI", strategy="Manual",
    )


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    init_state()

    alpaca, risk = init_components(
        Config.ALPACA_API_KEY,
        Config.ALPACA_SECRET_KEY,
        Config.ALPACA_BASE_URL,
    )

    order_manager = OrderManager(
        alpaca, risk,
        st.session_state.demo_portfolio,
    )

    # Sidebar — returns user selections
    strategy_name, selected_symbol, auto_trade = render_sidebar(alpaca)

    # Page header
    st.markdown("""
    <div style='text-align:center;padding:8px 0 20px 0'>
        <span style='font-family:Syne;font-weight:800;font-size:2rem;
                     background:linear-gradient(90deg,#00d4ff,#3a7bd5);
                     -webkit-background-clip:text;-webkit-text-fill-color:transparent'>
            AlgoTrader Pro
        </span>
        <span style='color:#6b7fa3;font-size:.9rem;margin-left:12px'>
            Algorithmic Trading Dashboard
        </span>
    </div>
    """, unsafe_allow_html=True)

    # Tabs
    tab1, tab2, tab3 = st.tabs(["📊  Dashboard", "🔬  Backtest", "📁  Portfolio"])

    with tab1:
        render_dashboard(
            alpaca, order_manager, risk,
            selected_symbol, strategy_name, auto_trade,
        )
    with tab2:
        render_backtest(selected_symbol, strategy_name)
    with tab3:
        render_portfolio(alpaca, order_manager)


if __name__ == "__main__":
    main()
