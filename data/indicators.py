"""
data/indicators.py — Pure-pandas technical indicator library.
No external TA libraries required — fully transparent implementations.
"""
import pandas as pd
import numpy as np


class TechnicalIndicators:
    """All indicators computed on pandas Series / DataFrame objects."""

    # ── Moving Averages ────────────────────────────────────────────────────────
    @staticmethod
    def sma(series: pd.Series, period: int) -> pd.Series:
        return series.rolling(window=period, min_periods=period).mean()

    @staticmethod
    def ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    # ── Bollinger Bands ────────────────────────────────────────────────────────
    @staticmethod
    def bollinger_bands(
        series: pd.Series, period: int = 20, std_dev: float = 2.0
    ) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
        """Returns (upper, mid, lower, %B)."""
        sma = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        upper = sma + std_dev * std
        lower = sma - std_dev * std
        pct_b = (series - lower) / (upper - lower + 1e-9)
        return upper, sma, lower, pct_b

    # ── RSI ────────────────────────────────────────────────────────────────────
    @staticmethod
    def rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta    = series.diff()
        gain     = delta.clip(lower=0)
        loss     = (-delta).clip(lower=0)
        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
        rs       = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    # ── MACD ──────────────────────────────────────────────────────────────────
    @staticmethod
    def macd(
        series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Returns (MACD line, signal line, histogram)."""
        ema_f   = series.ewm(span=fast,   adjust=False).mean()
        ema_s   = series.ewm(span=slow,   adjust=False).mean()
        line    = ema_f - ema_s
        sig     = line.ewm(span=signal, adjust=False).mean()
        hist    = line - sig
        return line, sig, hist

    # ── ATR ────────────────────────────────────────────────────────────────────
    @staticmethod
    def atr(
        high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
    ) -> pd.Series:
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs(),
        ], axis=1).max(axis=1)
        return tr.ewm(com=period - 1, min_periods=period).mean()

    # ── Volume SMA ─────────────────────────────────────────────────────────────
    @staticmethod
    def vol_sma(volume: pd.Series, period: int = 20) -> pd.Series:
        return volume.rolling(window=period).mean()

    # ── Stochastic Oscillator ──────────────────────────────────────────────────
    @staticmethod
    def stochastic(
        high: pd.Series, low: pd.Series, close: pd.Series,
        k_period: int = 14, d_period: int = 3
    ) -> tuple[pd.Series, pd.Series]:
        lo  = low.rolling(k_period).min()
        hi  = high.rolling(k_period).max()
        k   = 100 * (close - lo) / (hi - lo + 1e-9)
        d   = k.rolling(d_period).mean()
        return k, d

    # ── Convenience: enrich an OHLCV DataFrame with all indicators ─────────────
    @classmethod
    def add_all(cls, df: pd.DataFrame, cfg=None) -> pd.DataFrame:
        """
        Adds all indicators in-place.
        Expects columns: Open, High, Low, Close, Volume.
        """
        if cfg is None:
            from config import Config
            cfg = Config

        c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]

        # Moving averages
        df["SMA_20"]  = cls.sma(c, 20)
        df["SMA_50"]  = cls.sma(c, 50)
        df["EMA_20"]  = cls.ema(c, cfg.EMA_FAST)
        df["EMA_50"]  = cls.ema(c, cfg.EMA_SLOW)

        # Bollinger Bands
        df["BB_upper"], df["BB_mid"], df["BB_lower"], df["BB_pct"] = \
            cls.bollinger_bands(c, cfg.BB_PERIOD, cfg.BB_STD_DEV)

        # RSI
        df["RSI"] = cls.rsi(c, cfg.RSI_PERIOD)

        # MACD
        df["MACD"], df["MACD_signal"], df["MACD_hist"] = \
            cls.macd(c, cfg.MACD_FAST, cfg.MACD_SLOW, cfg.MACD_SIGNAL_PERIOD)

        # ATR
        df["ATR"] = cls.atr(h, l, c)

        # Volume SMA
        df["Vol_SMA"] = cls.vol_sma(v, 20)

        # Stochastic
        df["Stoch_K"], df["Stoch_D"] = cls.stochastic(h, l, c)

        return df
