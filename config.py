"""
config.py — Central configuration for AlgoTrader Pro.
All tuneable parameters live here; strategies & UI read from Config.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── Alpaca Credentials ────────────────────────────────────────────────────
    ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY", "")
    ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
    ALPACA_BASE_URL   = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    # ── Paper Portfolio ───────────────────────────────────────────────────────
    INITIAL_CAPITAL = float(os.getenv("INITIAL_CAPITAL", "100000"))

    # ── Default Watchlist ─────────────────────────────────────────────────────
    DEFAULT_WATCHLIST = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA",
        "NVDA", "META", "SPY", "QQQ", "AMD",
    ]

    # ── Risk Management ───────────────────────────────────────────────────────
    MAX_POSITION_PCT     = 0.10   # Max 10 % of portfolio per position
    RISK_PER_TRADE_PCT   = 0.01   # Risk 1 % of portfolio per trade (ATR-based)
    STOP_LOSS_PCT        = 0.02   # 2 % hard stop-loss from entry
    TAKE_PROFIT_PCT      = 0.04   # 4 % take-profit from entry
    MAX_OPEN_POSITIONS   = 5      # Concurrent position limit

    # ── Mean-Reversion (Bollinger Bands) ──────────────────────────────────────
    BB_PERIOD    = 20
    BB_STD_DEV   = 2.0
    MR_RSI_LOW   = 40    # Oversold confirmation threshold
    MR_RSI_HIGH  = 60    # Overbought confirmation threshold

    # ── Momentum (RSI + MACD) ─────────────────────────────────────────────────
    RSI_PERIOD         = 14
    RSI_OVERSOLD       = 30
    RSI_OVERBOUGHT     = 70
    MACD_FAST          = 12
    MACD_SLOW          = 26
    MACD_SIGNAL_PERIOD = 9
    EMA_FAST           = 20
    EMA_SLOW           = 50

    # ── Data ──────────────────────────────────────────────────────────────────
    DATA_LOOKBACK = "6mo"   # yfinance period string
    DATA_INTERVAL = "1d"

    # ── UI ────────────────────────────────────────────────────────────────────
    CHART_HEIGHT  = 620
    # Colour palette (used in chart & CSS)
    C_BG      = "#060b14"
    C_CARD    = "#0d1b2a"
    C_BORDER  = "#1a2e44"
    C_ACCENT  = "#00d4ff"
    C_GREEN   = "#00e5a0"
    C_RED     = "#ff3d5a"
    C_YELLOW  = "#ffd166"
    C_TEXT    = "#cdd6f4"
    C_MUTED   = "#6b7fa3"
