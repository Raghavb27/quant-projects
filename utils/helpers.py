"""
utils/helpers.py — Shared formatting and display helpers.
"""
from __future__ import annotations

import pandas as pd
from typing import Union


def fmt_currency(value: float, decimals: int = 2) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}${value:,.{decimals}f}" if value != 0 else f"${value:,.{decimals}f}"


def fmt_pct(value: float, decimals: int = 2) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.{decimals}f}%"


def color_value(value: float, positive_color: str = "#00e5a0", negative_color: str = "#ff3d5a") -> str:
    """Return an HTML-coloured span for a numeric value."""
    color = positive_color if value >= 0 else negative_color
    return f'<span style="color:{color}">{value:+,.2f}</span>'


def signal_badge(signal: str) -> str:
    """Return a coloured HTML badge for BUY / SELL / HOLD."""
    styles = {
        "BUY":  "background:#00e5a0;color:#000",
        "SELL": "background:#ff3d5a;color:#fff",
        "HOLD": "background:#ffd166;color:#000",
    }
    style = styles.get(signal, "background:#888;color:#fff")
    return f'<span style="{style};padding:2px 8px;border-radius:4px;font-weight:700;font-size:.75rem">{signal}</span>'


def confidence_bar(conf: float) -> str:
    """ASCII-style confidence bar."""
    filled = int(conf * 10)
    bar    = "█" * filled + "░" * (10 - filled)
    return f"{bar} {conf:.0%}"


def df_to_display(df: pd.DataFrame, pct_cols=(), currency_cols=(), signal_cols=()) -> pd.DataFrame:
    """Return a copy of df with formatted columns for st.dataframe display."""
    out = df.copy()
    for c in pct_cols:
        if c in out:
            out[c] = out[c].apply(lambda x: fmt_pct(x) if pd.notna(x) else "—")
    for c in currency_cols:
        if c in out:
            out[c] = out[c].apply(lambda x: f"${x:,.2f}" if pd.notna(x) else "—")
    return out
