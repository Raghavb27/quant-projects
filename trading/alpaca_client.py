"""
trading/alpaca_client.py — Alpaca paper-trading API wrapper.

Gracefully degrades to demo mode when:
  • alpaca-trade-api is not installed, or
  • credentials are blank / invalid.

All live-trading calls are NO-OPs in demo mode; the app simulates everything
locally in session state instead.
"""
from __future__ import annotations

from typing import Dict, List, Optional

try:
    import streamlit as st
    _HAS_ST = True
except ImportError:
    _HAS_ST = False

def _warn(msg: str) -> None:
    if _HAS_ST:
        st.warning(msg)
    else:
        print("WARNING:", msg)


class AlpacaClient:
    """Thin wrapper around alpaca_trade_api.REST with demo-mode fallback."""

    def __init__(self, api_key: str, secret_key: str, base_url: str):
        self.connected = False
        self.api: Optional[object] = None
        self._connect(api_key, secret_key, base_url)

    # ── Connection ─────────────────────────────────────────────────────────────

    def _connect(self, api_key: str, secret_key: str, base_url: str) -> None:
        if not api_key or not secret_key:
            return   # demo mode silently

        try:
            import alpaca_trade_api as tradeapi
            self.api = tradeapi.REST(api_key, secret_key, base_url, api_version="v2")
            self.api.get_account()        # live validation call
            self.connected = True
        except ImportError:
            _warn(
                "⚠️  `alpaca-trade-api` not installed. "
                "Run `pip install alpaca-trade-api` to enable live paper trading."
            )
        except Exception as exc:
            _warn(f"⚠️  Alpaca connection failed ({exc}). Running in demo mode.")

    # ── Account ────────────────────────────────────────────────────────────────

    def get_account(self) -> Optional[Dict]:
        if not self.connected:
            return None
        try:
            a = self.api.get_account()
            return {
                "portfolio_value": float(a.portfolio_value),
                "equity":          float(a.equity),
                "cash":            float(a.cash),
                "buying_power":    float(a.buying_power),
                "pnl":             float(a.equity) - float(a.last_equity),
            }
        except Exception:
            return None

    # ── Positions ──────────────────────────────────────────────────────────────

    def get_positions(self) -> List[Dict]:
        if not self.connected:
            return []
        try:
            return [
                {
                    "symbol":   p.symbol,
                    "qty":      float(p.qty),
                    "avg_cost": float(p.avg_entry_price),
                    "price":    float(p.current_price),
                    "mkt_val":  float(p.market_value),
                    "pnl":      float(p.unrealized_pl),
                    "pnl_pct":  float(p.unrealized_plpc) * 100,
                }
                for p in self.api.list_positions()
            ]
        except Exception:
            return []

    # ── Orders ─────────────────────────────────────────────────────────────────

    def submit_market_order(
        self, symbol: str, qty: int, side: str   # side: "buy" | "sell"
    ) -> Optional[Dict]:
        if not self.connected:
            return None
        try:
            o = self.api.submit_order(
                symbol=symbol,
                qty=max(1, qty),
                side=side,
                type="market",
                time_in_force="day",
            )
            return {
                "id":     o.id,
                "symbol": o.symbol,
                "qty":    float(o.qty),
                "side":   o.side,
                "status": o.status,
            }
        except Exception as exc:
            _warn(f"Order error ({symbol} {side}): {exc}")
            return None

    def get_orders(self, status: str = "all", limit: int = 25) -> List[Dict]:
        if not self.connected:
            return []
        try:
            return [
                {
                    "id":          o.id,
                    "symbol":      o.symbol,
                    "qty":         float(o.qty),
                    "side":        o.side,
                    "status":      o.status,
                    "submitted":   str(o.submitted_at)[:19],
                    "filled_avg":  float(o.filled_avg_price or 0),
                }
                for o in self.api.list_orders(status=status, limit=limit)
            ]
        except Exception:
            return []

    def cancel_order(self, order_id: str) -> bool:
        if not self.connected:
            return False
        try:
            self.api.cancel_order(order_id)
            return True
        except Exception:
            return False
