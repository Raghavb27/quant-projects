"""
strategies/momentum.py — RSI + MACD Momentum Strategy.

Logic:
  Strong BUY  : RSI < oversold  AND MACD bullish crossover AND price > EMA50
  Weak   BUY  : RSI crosses 50↑ OR  MACD hist turns positive AND price > EMA20
  Strong SELL : RSI > overbought AND MACD bearish crossover AND price < EMA50
  Weak   SELL : RSI crosses 50↓ OR  MACD hist turns negative AND price < EMA20
  HOLD        : no conditions met
"""
from __future__ import annotations

import pandas as pd
from strategies.base_strategy import BaseStrategy, Signal


class MomentumStrategy(BaseStrategy):
    name = "Momentum (RSI+MACD)"

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Signal:
        if not self._validate(df):
            return self._insufficient_data(symbol)

        row  = df.iloc[-1]
        prev = df.iloc[-2]

        price        = float(row["Close"])
        rsi          = float(row["RSI"])
        prev_rsi     = float(prev["RSI"])
        macd_hist    = float(row["MACD_hist"])
        prev_hist    = float(prev["MACD_hist"])
        macd         = float(row["MACD"])
        macd_sig     = float(row["MACD_signal"])
        ema20        = float(row["EMA_20"])
        ema50        = float(row["EMA_50"])

        # Crossover flags
        macd_cross_up   = macd_hist > 0  and prev_hist <= 0
        macd_cross_down = macd_hist < 0  and prev_hist >= 0
        rsi_cross_up    = rsi       > 50 and prev_rsi  <= 50
        rsi_cross_down  = rsi       < 50 and prev_rsi  >= 50

        # ── Strong BUY ─────────────────────────────────────────────────────────
        if rsi < self.cfg.RSI_OVERSOLD and macd > macd_sig and price > ema50:
            conf   = self._conf_buy(rsi, macd_hist, price, ema50)
            reason = (
                f"RSI {rsi:.1f} oversold | MACD bullish | "
                f"Price {price:.2f} above EMA50 {ema50:.2f}"
            )
            return Signal(symbol, "BUY", price, conf, reason, self.name)

        # ── Weak BUY ───────────────────────────────────────────────────────────
        if (rsi_cross_up or macd_cross_up) and price > ema20:
            parts = []
            if rsi_cross_up:    parts.append(f"RSI crossed 50↑ ({rsi:.1f})")
            if macd_cross_up:   parts.append("MACD histogram turned positive")
            reason = " | ".join(parts) + f" | Price above EMA20 {ema20:.2f}"
            return Signal(symbol, "BUY", price, 0.60, reason, self.name)

        # ── Strong SELL ────────────────────────────────────────────────────────
        if rsi > self.cfg.RSI_OVERBOUGHT and macd < macd_sig and price < ema50:
            conf   = self._conf_sell(rsi, macd_hist, price, ema50)
            reason = (
                f"RSI {rsi:.1f} overbought | MACD bearish | "
                f"Price {price:.2f} below EMA50 {ema50:.2f}"
            )
            return Signal(symbol, "SELL", price, conf, reason, self.name)

        # ── Weak SELL ──────────────────────────────────────────────────────────
        if (rsi_cross_down or macd_cross_down) and price < ema20:
            parts = []
            if rsi_cross_down:  parts.append(f"RSI crossed 50↓ ({rsi:.1f})")
            if macd_cross_down: parts.append("MACD histogram turned negative")
            reason = " | ".join(parts) + f" | Price below EMA20 {ema20:.2f}"
            return Signal(symbol, "SELL", price, 0.60, reason, self.name)

        # ── HOLD ───────────────────────────────────────────────────────────────
        trend = "↑" if price > ema50 else "↓"
        reason = (
            f"RSI {rsi:.1f} | MACD hist {macd_hist:+.3f} | "
            f"Trend {trend} (price vs EMA50 {((price/ema50-1)*100):+.1f}%)"
        )
        return Signal(symbol, "HOLD", price, 0.5, reason, self.name)

    # ── Confidence helpers ─────────────────────────────────────────────────────

    def _conf_buy(self, rsi, macd_hist, price, ema50):
        rsi_s   = (self.cfg.RSI_OVERSOLD - rsi) / max(self.cfg.RSI_OVERSOLD, 1)
        macd_s  = min(1.0, abs(macd_hist) / 0.5)
        trend_s = min(1.0, max(0.0, (price / ema50 - 1) * 10))
        return round(min(1.0, 0.5 + (rsi_s + macd_s + trend_s) / 6), 2)

    def _conf_sell(self, rsi, macd_hist, price, ema50):
        rsi_s   = (rsi - self.cfg.RSI_OVERBOUGHT) / max(100 - self.cfg.RSI_OVERBOUGHT, 1)
        macd_s  = min(1.0, abs(macd_hist) / 0.5)
        trend_s = min(1.0, max(0.0, (1 - price / ema50) * 10))
        return round(min(1.0, 0.5 + (rsi_s + macd_s + trend_s) / 6), 2)
