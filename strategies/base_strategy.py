"""
strategies/base_strategy.py — Abstract base class for all trading strategies.

Includes a built-in walk-forward backtester so every strategy can be
evaluated without extra code.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal, List, Dict, Any
import pandas as pd
import numpy as np

SignalType = Literal["BUY", "SELL", "HOLD"]


# ── Signal dataclass ───────────────────────────────────────────────────────────

@dataclass
class Signal:
    symbol:     str
    signal:     SignalType
    price:      float
    confidence: float               # 0.0 – 1.0
    reason:     str
    strategy:   str
    timestamp:  pd.Timestamp = field(default_factory=pd.Timestamp.now)

    @property
    def emoji(self) -> str:
        return {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}[self.signal]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "Symbol":     self.symbol,
            "Signal":     self.signal,
            "Price":      self.price,
            "Confidence": f"{self.confidence:.0%}",
            "Reason":     self.reason,
            "Strategy":   self.strategy,
            "Time":       self.timestamp.strftime("%H:%M:%S"),
        }


# ── Base Strategy ──────────────────────────────────────────────────────────────

class BaseStrategy(ABC):
    name: str = "Base"

    def __init__(self, cfg=None):
        from config import Config
        self.cfg = cfg or Config

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Signal:
        """Derive a trading signal from a fully-enriched OHLCV+indicator DF."""
        ...

    def _insufficient_data(self, symbol: str) -> Signal:
        return Signal(
            symbol=symbol, signal="HOLD", price=0.0,
            confidence=0.0, reason="Insufficient data (need ≥ 60 bars)",
            strategy=self.name,
        )

    def _validate(self, df: pd.DataFrame) -> bool:
        return df is not None and len(df) >= 60 and "RSI" in df.columns

    # ── Walk-forward backtester ────────────────────────────────────────────────

    def backtest(
        self,
        df: pd.DataFrame,
        symbol: str,
        initial_capital: float = 100_000.0,
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
    ) -> Dict[str, Any]:
        """
        Simple event-driven backtester.
        Iterates through the DataFrame one bar at a time, generating signals
        on the visible history up to that point (no look-ahead bias).

        Returns:
            dict with performance metrics + equity curve + trade list.
        """
        from config import Config
        sl_pct = stop_loss_pct  or Config.STOP_LOSS_PCT
        tp_pct = take_profit_pct or Config.TAKE_PROFIT_PCT

        capital     = initial_capital
        position    = 0          # shares held
        entry_price = 0.0
        equity_curve: List[float] = []
        trades:       List[Dict]  = []

        warmup = 60   # bars needed for indicators

        for i in range(warmup, len(df)):
            window = df.iloc[: i + 1].copy()
            bar    = df.iloc[i]
            price  = float(bar["Close"])

            # ── Check stop-loss / take-profit on open position ────────────────
            if position > 0:
                pnl_pct = (price - entry_price) / entry_price
                if pnl_pct <= -sl_pct or pnl_pct >= tp_pct:
                    reason  = "Stop-loss" if pnl_pct <= -sl_pct else "Take-profit"
                    proceeds = position * price
                    capital += proceeds
                    trades.append({
                        "date":   df.index[i],
                        "type":   "SELL",
                        "price":  price,
                        "shares": position,
                        "pnl":    (price - entry_price) * position,
                        "reason": reason,
                    })
                    position    = 0
                    entry_price = 0.0

            # ── Strategy signal ───────────────────────────────────────────────
            sig = self.generate_signal(window, symbol)

            if sig.signal == "BUY" and position == 0:
                shares = max(1, int(capital * 0.95 / price))
                cost   = shares * price
                if cost <= capital:
                    position    = shares
                    entry_price = price
                    capital    -= cost
                    trades.append({
                        "date":   df.index[i],
                        "type":   "BUY",
                        "price":  price,
                        "shares": shares,
                        "pnl":    None,
                        "reason": sig.reason[:60],
                    })

            elif sig.signal == "SELL" and position > 0:
                proceeds = position * price
                capital += proceeds
                trades.append({
                    "date":   df.index[i],
                    "type":   "SELL",
                    "price":  price,
                    "shares": position,
                    "pnl":    (price - entry_price) * position,
                    "reason": sig.reason[:60],
                })
                position    = 0
                entry_price = 0.0

            # Track equity each bar
            equity_curve.append(capital + position * price)

        # Force-close any remaining position at last price
        if position > 0:
            last_price = float(df["Close"].iloc[-1])
            capital   += position * last_price

        # ── Performance metrics ───────────────────────────────────────────────
        equity_s = pd.Series(equity_curve)
        returns  = equity_s.pct_change().dropna()

        sell_trades  = [t for t in trades if t["type"] == "SELL" and t["pnl"] is not None]
        winning      = [t for t in sell_trades if t["pnl"] > 0]
        total_return = (capital - initial_capital) / initial_capital * 100

        # Sharpe (annualised, daily returns, rf=0)
        sharpe = 0.0
        if len(returns) > 1 and returns.std() > 0:
            sharpe = float((returns.mean() / returns.std()) * np.sqrt(252))

        # Max drawdown
        peak    = equity_s.cummax()
        dd      = (equity_s - peak) / peak
        max_dd  = float(dd.min() * 100)

        return {
            "symbol":         symbol,
            "strategy":       self.name,
            "initial":        initial_capital,
            "final":          round(capital, 2),
            "total_return":   round(total_return, 2),
            "sharpe":         round(sharpe, 2),
            "max_drawdown":   round(max_dd, 2),
            "n_trades":       len(sell_trades),
            "win_rate":       round(len(winning) / len(sell_trades) * 100, 1) if sell_trades else 0.0,
            "avg_pnl":        round(sum(t["pnl"] for t in sell_trades) / len(sell_trades), 2) if sell_trades else 0.0,
            "equity_curve":   equity_curve,
            "equity_index":   df.index[60:].tolist(),
            "trades":         trades,
        }
