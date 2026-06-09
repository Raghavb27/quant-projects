"""
trading/order_manager.py — Routes strategy signals through risk checks
                           and into either live Alpaca orders or demo simulation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from strategies.base_strategy import Signal
from trading.alpaca_client import AlpacaClient
from trading.risk_manager import RiskManager


class OrderManager:
    """
    Receives a Signal, applies risk sizing, and executes.

    demo_portfolio is a dict kept in st.session_state:
        {
            "cash":      float,
            "positions": {symbol: {"qty": int, "avg_cost": float, "price": float}},
            "trade_log": [trade_dict, ...],
        }
    """

    def __init__(
        self,
        alpaca: AlpacaClient,
        risk: RiskManager,
        demo_portfolio: Dict,
    ):
        self.alpaca = alpaca
        self.risk   = risk
        self.demo   = demo_portfolio   # reference to session_state dict

    # ── Public API ─────────────────────────────────────────────────────────────

    def execute(self, signal: Signal, latest_bar: dict) -> Optional[Dict]:
        """Execute a signal. Returns order dict or None if skipped."""
        if signal.signal == "HOLD":
            return None

        n_open = len(self._open_positions())
        if signal.signal == "BUY" and not self.risk.can_open(n_open):
            return None

        if signal.signal == "SELL":
            # Close the full position rather than a partial risk-sized lot
            positions = self.demo.get("positions", {})
            if not self.alpaca.connected and signal.symbol not in positions:
                return None
            qty = int(positions[signal.symbol]["qty"]) if signal.symbol in positions else 0
            if qty == 0:
                return None
        else:
            atr = float(latest_bar.get("ATR") or signal.price * 0.02)
            qty = self.risk.position_size(self._portfolio_value(), signal.price, atr)
            if qty == 0:
                return None

        side = "buy" if signal.signal == "BUY" else "sell"

        if self.alpaca.connected:
            order = self.alpaca.submit_market_order(signal.symbol, qty, side)
            if order:
                self._log(signal, qty, side, "live")
            return order
        else:
            return self._demo_fill(signal, qty, side)

    def manual_order(self, symbol: str, qty: int, side: str, price: float) -> Dict:
        """Place a manual market order (from the UI trade panel)."""
        sig = Signal(
            symbol=symbol, signal="BUY" if side == "buy" else "SELL",
            price=price, confidence=1.0,
            reason="Manual order", strategy="Manual",
        )
        if self.alpaca.connected:
            order = self.alpaca.submit_market_order(symbol, qty, side)
            if order:
                self._log(sig, qty, side, "live")
            return order or {}
        return self._demo_fill(sig, qty, side)

    def get_trade_log(self) -> List[Dict]:
        return self.demo.get("trade_log", [])

    def get_demo_positions(self) -> List[Dict]:
        positions = self.demo.get("positions", {})
        result = []
        for sym, p in positions.items():
            cost   = p["avg_cost"]
            price  = p["price"]
            pnl    = (price - cost) * p["qty"]
            pnl_pct = (price / cost - 1) * 100 if cost else 0
            result.append({
                "symbol":   sym,
                "qty":      p["qty"],
                "avg_cost": round(cost,    2),
                "price":    round(price,   2),
                "mkt_val":  round(price * p["qty"], 2),
                "pnl":      round(pnl,     2),
                "pnl_pct":  round(pnl_pct, 2),
            })
        return result

    def update_demo_prices(self, quotes: Dict[str, float]) -> None:
        """Refresh current prices in demo positions."""
        positions = self.demo.get("positions", {})
        for sym, price in quotes.items():
            if sym in positions:
                positions[sym]["price"] = price
        self.demo["positions"] = positions

    # ── Demo execution ─────────────────────────────────────────────────────────

    def _demo_fill(self, signal: Signal, qty: int, side: str) -> Dict:
        positions = self.demo.setdefault("positions", {})
        cash      = self.demo.get("cash", 100_000.0)

        if side == "buy":
            cost = signal.price * qty
            if cost > cash:
                qty  = max(1, int(cash * 0.95 / signal.price))
                cost = signal.price * qty
            if qty == 0 or cost > cash:
                return {}

            self.demo["cash"] = cash - cost
            if signal.symbol in positions:
                p = positions[signal.symbol]
                total   = p["qty"] + qty
                avg     = (p["avg_cost"] * p["qty"] + signal.price * qty) / total
                positions[signal.symbol] = {"qty": total, "avg_cost": avg, "price": signal.price}
            else:
                positions[signal.symbol] = {
                    "qty": qty, "avg_cost": signal.price, "price": signal.price
                }

        elif side == "sell":
            if signal.symbol not in positions:
                return {}
            p        = positions[signal.symbol]
            sell_qty = min(qty, int(p["qty"]))
            self.demo["cash"] = cash + signal.price * sell_qty
            remaining = p["qty"] - sell_qty
            if remaining <= 0:
                del positions[signal.symbol]
            else:
                positions[signal.symbol]["qty"] = remaining

        self.demo["positions"] = positions
        self._log(signal, qty, side, "demo")

        return {
            "symbol": signal.symbol,
            "qty":    qty,
            "side":   side,
            "price":  signal.price,
            "status": "filled (demo)",
        }

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _log(self, signal: Signal, qty: int, side: str, mode: str) -> None:
        trade = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "symbol":    signal.symbol,
            "side":      side.upper(),
            "qty":       qty,
            "price":     round(signal.price, 2),
            "value":     round(signal.price * qty, 2),
            "strategy":  signal.strategy,
            "mode":      mode,
        }
        log = self.demo.setdefault("trade_log", [])
        log.insert(0, trade)
        self.demo["trade_log"] = log[:200]   # keep last 200 trades

    def _portfolio_value(self) -> float:
        if self.alpaca.connected:
            acc = self.alpaca.get_account()
            return acc["portfolio_value"] if acc else 100_000.0
        cash = self.demo.get("cash", 100_000.0)
        pos  = sum(
            p["price"] * p["qty"]
            for p in self.demo.get("positions", {}).values()
        )
        return cash + pos

    def _open_positions(self) -> List:
        if self.alpaca.connected:
            return self.alpaca.get_positions()
        return list(self.demo.get("positions", {}).items())
