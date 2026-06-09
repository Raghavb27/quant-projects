"""
trading/risk_manager.py — Position sizing and portfolio-level risk controls.

Uses ATR-based position sizing:
  Shares = (portfolio * risk_pct) / (2 × ATR)
  Capped at max_position_pct of portfolio.
"""
from __future__ import annotations


class RiskManager:

    def __init__(self, cfg=None):
        from config import Config
        self.cfg = cfg or Config

    # ── Position Sizing ────────────────────────────────────────────────────────

    def position_size(
        self,
        portfolio_value: float,
        price: float,
        atr: float,
    ) -> int:
        """Return number of shares to buy, respecting all risk limits."""
        if price <= 0 or atr <= 0:
            return 0

        risk_dollars   = portfolio_value * self.cfg.RISK_PER_TRADE_PCT
        stop_distance  = 2.0 * atr                  # 2×ATR stop
        shares_by_risk = risk_dollars / stop_distance

        max_shares     = (portfolio_value * self.cfg.MAX_POSITION_PCT) / price
        shares         = min(shares_by_risk, max_shares)
        return max(1, int(shares))

    # ── Exit Levels ────────────────────────────────────────────────────────────

    def stop_loss(self, entry: float) -> float:
        return round(entry * (1 - self.cfg.STOP_LOSS_PCT), 4)

    def take_profit(self, entry: float) -> float:
        return round(entry * (1 + self.cfg.TAKE_PROFIT_PCT), 4)

    # ── Portfolio Guards ───────────────────────────────────────────────────────

    def can_open(self, n_open: int) -> bool:
        return n_open < self.cfg.MAX_OPEN_POSITIONS

    def risk_reward(self) -> float:
        return self.cfg.TAKE_PROFIT_PCT / self.cfg.STOP_LOSS_PCT

    def max_loss_per_trade(self, portfolio_value: float) -> float:
        return round(portfolio_value * self.cfg.RISK_PER_TRADE_PCT, 2)

    def position_summary(self, portfolio_value: float, price: float, atr: float) -> dict:
        qty = self.position_size(portfolio_value, price, atr)
        return {
            "shares":      qty,
            "cost":        round(qty * price, 2),
            "stop_loss":   self.stop_loss(price),
            "take_profit": self.take_profit(price),
            "max_loss":    round(qty * price * self.cfg.STOP_LOSS_PCT, 2),
            "risk_reward": self.risk_reward(),
        }
