# 📈 AlgoTrader Pro — Algorithmic Trading Dashboard

A full-stack algorithmic trading dashboard built with **Python + Streamlit**, featuring live market data, two trading strategies (mean-reversion & momentum), ATR-based risk management, a walk-forward backtester, and optional **Alpaca paper-trading** execution.

> Works **100% out of the box** in demo mode — no API keys needed.  
> Add Alpaca credentials for real paper-order execution.

---

## ✨ Features

| Feature | Description |
|---|---|
| 📊 **Live Dashboard** | Real-time OHLCV charts (candlestick + volume + oscillator) with Plotly |
| 🎯 **Signal Generation** | BUY/SELL/HOLD signals with confidence scores for every watchlist symbol |
| 🔬 **Walk-Forward Backtester** | No-look-ahead backtest with equity curve, Sharpe, max drawdown & trade log |
| 💰 **Risk Management** | ATR-based position sizing, stop-loss, take-profit, max-position guards |
| 🤖 **Two Strategies** | Bollinger Band Mean-Reversion + RSI/MACD Momentum |
| 🏦 **Alpaca Integration** | Paper-trade execution via Alpaca REST API (v2) |
| 🔄 **Demo Mode** | Fully simulated $100k portfolio in session state — no credentials needed |
| 🛠 **Manual Orders** | Place manual buy/sell orders from the sidebar UI |

---

## 🚀 Quick Start

### 1. Clone & install

```bash
git clone https://github.com/<your-username>/trading-dashboard.git
cd trading-dashboard
pip install -r requirements.txt
```

### 2. Configure (optional — for live paper trading)

```bash
cp .env.example .env
# Edit .env and add your Alpaca API key + secret
```

Get free paper-trading credentials at **[alpaca.markets](https://alpaca.markets)** → no real money required.

### 3. Run

```bash
streamlit run app.py
```

Opens at `http://localhost:8501` in your browser.

---

## 🗂 Project Structure

```
trading-dashboard/
├── app.py                    # ← Main Streamlit app (UI + orchestration)
├── config.py                 # All tuneable parameters in one place
├── requirements.txt
├── .env.example              # Credential template
│
├── data/
│   ├── indicators.py         # Pure-pandas: BB, RSI, MACD, ATR, Stochastic
│   └── market_data.py        # yfinance fetch + Streamlit cache
│
├── strategies/
│   ├── base_strategy.py      # Abstract base + built-in walk-forward backtester
│   ├── mean_reversion.py     # Bollinger Band strategy
│   └── momentum.py           # RSI + MACD strategy
│
├── trading/
│   ├── alpaca_client.py      # Alpaca REST wrapper (graceful demo fallback)
│   ├── risk_manager.py       # ATR position sizing, stop/TP levels
│   └── order_manager.py      # Signal → risk check → execution bridge
│
└── utils/
    └── helpers.py            # Formatting utilities
```

---

## 📐 Strategy Logic

### 🔵 Mean Reversion (Bollinger Bands)

| Condition | Signal |
|---|---|
| `Close < Lower BB` **AND** `RSI < 40` | **BUY** |
| `Close > Upper BB` **AND** `RSI > 60` | **SELL** |
| Price inside bands | HOLD |

### 🟠 Momentum (RSI + MACD)

| Condition | Signal |
|---|---|
| `RSI < 30` AND MACD bullish AND `price > EMA50` | **Strong BUY** |
| RSI crosses 50↑ OR MACD histogram turns positive AND `price > EMA20` | **Weak BUY** |
| `RSI > 70` AND MACD bearish AND `price < EMA50` | **Strong SELL** |
| RSI crosses 50↓ OR MACD histogram turns negative AND `price < EMA20` | **Weak SELL** |

---

## ⚖️ Risk Management

Position size is calculated using the **ATR (Average True Range)** method:

```
Risk dollars  = Portfolio × RISK_PER_TRADE_PCT   (default 1%)
Stop distance = 2 × ATR
Shares        = min(Risk$ / Stop, Portfolio × MAX_POSITION_PCT / Price)
```

Default parameters (all configurable in `config.py`):

| Parameter | Default |
|---|---|
| Stop Loss | 2% |
| Take Profit | 4% |
| Max Position | 10% of portfolio |
| Max Open Positions | 5 |
| Risk per Trade | 1% |

---

## 🔬 Backtester

The built-in walk-forward backtester (in `BaseStrategy.backtest()`) iterates through historical data one bar at a time — the strategy only sees data up to the current bar, eliminating look-ahead bias.

**Metrics reported:**
- Total return %
- Sharpe ratio (annualised, rf = 0)
- Maximum drawdown
- Win rate & number of trades
- Average trade P&L
- Full equity curve chart
- Complete trade history table

---

## 🏦 Alpaca Integration

The app connects to Alpaca's **paper trading** endpoint (free, no real money):

```
Base URL: https://paper-api.alpaca.markets
```

When connected, the app:
- Fetches live account balance, buying power, and positions
- Executes real paper orders (market orders, day TIF)
- Displays Alpaca order history

When credentials are absent or invalid, the app silently falls back to demo mode (local session-state simulation).

---

## ⚙️ Configuration

All parameters are in `config.py`. Key settings:

```python
INITIAL_CAPITAL    = 100_000    # Demo portfolio starting value
STOP_LOSS_PCT      = 0.02       # 2% stop loss
TAKE_PROFIT_PCT    = 0.04       # 4% take profit
MAX_OPEN_POSITIONS = 5
RISK_PER_TRADE_PCT = 0.01       # 1% of portfolio at risk per trade
BB_PERIOD          = 20
RSI_PERIOD         = 14
RSI_OVERSOLD       = 30
RSI_OVERBOUGHT     = 70
```

---

## 🛠 Tech Stack

| Layer | Technology |
|---|---|
| UI / App | Streamlit |
| Charts | Plotly |
| Market Data | yfinance |
| Broker API | Alpaca Trade API v2 |
| Indicators | Pure pandas/numpy (no TA-Lib) |
| Language | Python 3.10+ |

---

## 📌 Extending the Project

- **Add a new strategy** → subclass `BaseStrategy`, implement `generate_signal()`, register in `STRATEGIES` dict in `app.py`
- **Add an indicator** → add a static method to `TechnicalIndicators` and call it in `add_all()`
- **Change data source** → replace `fetch_historical()` in `market_data.py`
- **Add options/crypto** → Alpaca supports both; update the symbol format and order parameters

---

## ⚠️ Disclaimer

This project is for **educational and portfolio purposes only**.  
It does **not** constitute financial advice. Past backtested performance does not guarantee future results.  
Always paper-trade before committing real capital.

---

## 📄 License

MIT — free to use, modify, and distribute.
# quant-projects
