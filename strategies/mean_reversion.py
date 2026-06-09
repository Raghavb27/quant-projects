"""
strategies/mean_reversion.py — Bollinger Band Mean-Reversion Strategy.

Logic:
  BUY  → price closes BELOW lower BB  AND  RSI < MR_RSI_LOW  (double confirmation)
  SELL → price closes ABOVE upper BB  AND  RSI > MR_RSI_HIGH
  HOLD → price inside bands or confirmation missing
"""
from __future__ import annotations

import pandas as pd
from strategies.base_strategy import BaseStrategy, Signal


class MeanReversionStrategy(BaseStrategy):
    name = "Mean Reversion (BB)"

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Signal:
        if not self._validate(df):
            return self._insufficient_data(symbol)

        row  = df.iloc[-1]
        price     = float(row["Close"])
        bb_upper  = float(row["BB_upper"])
        bb_lower  = float(row["BB_lower"])
        bb_mid    = float(row["BB_mid"])
        rsi       = float(row["RSI"])
        bb_pct    = float(row["BB_pct"])
        atr       = float(row.get("ATR", price * 0.02))

        # ── BUY conditions ─────────────────────────────────────────────────────
        if price < bb_lower and rsi < self.cfg.MR_RSI_LOW:
            conf   = self._confidence_buy(rsi, bb_pct)
            reason = (
                f"Price {price:.2f} < Lower BB {bb_lower:.2f} | "
                f"RSI {rsi:.1f} < {self.cfg.MR_RSI_LOW}"
            )
            return Signal(symbol, "BUY", price, conf, reason, self.name)

        # ── SELL conditions ────────────────────────────────────────────────────
        if price > bb_upper and rsi > self.cfg.MR_RSI_HIGH:
            conf   = self._confidence_sell(rsi, bb_pct)
            reason = (
                f"Price {price:.2f} > Upper BB {bb_upper:.2f} | "
                f"RSI {rsi:.1f} > {self.cfg.MR_RSI_HIGH}"
            )
            return Signal(symbol, "SELL", price, conf, reason, self.name)

        # ── HOLD ───────────────────────────────────────────────────────────────
        reason = (
            f"Price inside BB ({bb_lower:.2f} – {bb_upper:.2f}) | "
            f"RSI {rsi:.1f} | %B {bb_pct:.2f}"
        )
        return Signal(symbol, "HOLD", price, 0.5, reason, self.name)

    # ── Confidence helpers ─────────────────────────────────────────────────────

    def _confidence_buy(self, rsi: float, bb_pct: float) -> float:
        rsi_score = max(0.0, (self.cfg.MR_RSI_LOW - rsi) / self.cfg.MR_RSI_LOW)
        bb_score  = max(0.0, -bb_pct)          # how far below 0 (below lower BB)
        return round(min(1.0, 0.5 + (rsi_score + bb_score) / 2), 2)

    def _confidence_sell(self, rsi: float, bb_pct: float) -> float:
        rsi_score = max(0.0, (rsi - self.cfg.MR_RSI_HIGH) / (100 - self.cfg.MR_RSI_HIGH))
        bb_score  = max(0.0, bb_pct - 1.0)     # how far above 1 (above upper BB)
        return round(min(1.0, 0.5 + (rsi_score + bb_score) / 2), 2)
