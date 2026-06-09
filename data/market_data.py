"""
data/market_data.py — OHLCV data fetching.

Primary source  : yfinance (free, no API key required)
Optional source : Alpaca real-time quotes (if connected)

Results are Streamlit-cached for 5 minutes when running inside the app.
When imported outside Streamlit (tests, scripts) caching is a no-op.
"""
from __future__ import annotations

import pandas as pd
from typing import Dict, List, Optional

from data.indicators import TechnicalIndicators

# ── Optional Streamlit caching ────────────────────────────────────────────────
try:
    import streamlit as st
    def _cache(fn):
        return st.cache_data(ttl=300, show_spinner=False)(fn)
except ImportError:
    def _cache(fn):          # no-op decorator outside Streamlit
        return fn

try:
    import yfinance as yf
    _HAS_YF = True
except ImportError:
    _HAS_YF = False
    yf = None  # type: ignore


# ── Core fetch functions ──────────────────────────────────────────────────────

@_cache
def fetch_historical(symbol: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    """Download OHLCV history and enrich with all technical indicators."""
    if not _HAS_YF:
        print("WARNING: yfinance not installed. Run: pip install yfinance")
        return pd.DataFrame()
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval, auto_adjust=True)

        if df.empty:
            return pd.DataFrame()

        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df.dropna(inplace=True)

        if len(df) < 60:
            return df

        df = TechnicalIndicators.add_all(df)
        return df

    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return pd.DataFrame()


@_cache
def fetch_quote(symbol: str) -> Dict:
    """Fetch latest price snapshot (cached 60 s inside Streamlit)."""
    if not _HAS_YF:
        return {}
    try:
        hist = yf.Ticker(symbol).history(period="5d", interval="1d", auto_adjust=True)
        if hist.empty or len(hist) < 2:
            return {}

        cur  = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2])
        chg  = cur - prev
        chg_pct = chg / prev * 100

        return {
            "symbol":     symbol,
            "price":      round(cur,     2),
            "change":     round(chg,     2),
            "change_pct": round(chg_pct, 2),
            "volume":     int(hist["Volume"].iloc[-1]),
            "high":       round(float(hist["High"].iloc[-1]),  2),
            "low":        round(float(hist["Low"].iloc[-1]),   2),
            "open":       round(float(hist["Open"].iloc[-1]),  2),
        }
    except Exception:
        return {}


def fetch_quotes_bulk(symbols: List[str]) -> pd.DataFrame:
    rows = [q for sym in symbols if (q := fetch_quote(sym))]
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def get_alpaca_quote(symbol: str, alpaca_client) -> Optional[Dict]:
    if alpaca_client and alpaca_client.connected:
        try:
            trade = alpaca_client.api.get_latest_trade(symbol)
            return {"symbol": symbol, "price": float(trade.price)}
        except Exception:
            pass
    return fetch_quote(symbol)
