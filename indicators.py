"""
indicators.py
Computes technical indicators used for both swing and intraday scoring.
"""

import pandas as pd
import pandas_ta as ta


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Takes a daily OHLCV DataFrame (columns: Open, High, Low, Close, Volume)
    and appends technical indicator columns. Returns the enriched DataFrame.
    """
    if df is None or df.empty or len(df) < 60:
        return pd.DataFrame()  # not enough history for reliable indicators

    out = df.copy()
    out.columns = [c.capitalize() if isinstance(c, str) else c for c in out.columns]

    out["EMA20"] = ta.ema(out["Close"], length=20)
    out["EMA50"] = ta.ema(out["Close"], length=50)
    out["EMA200"] = ta.ema(out["Close"], length=200) if len(out) >= 200 else None

    out["RSI14"] = ta.rsi(out["Close"], length=14)

    macd = ta.macd(out["Close"])
    if macd is not None:
        out["MACD"] = macd.iloc[:, 0]
        out["MACD_signal"] = macd.iloc[:, 1]
        out["MACD_hist"] = macd.iloc[:, 2]

    out["ATR14"] = ta.atr(out["High"], out["Low"], out["Close"], length=14)

    out["VolAvg20"] = out["Volume"].rolling(20).mean()
    out["VolSpike"] = out["Volume"] / out["VolAvg20"]

    # Simple support/resistance proxy: 20-day high/low
    out["High20"] = out["High"].rolling(20).max()
    out["Low20"] = out["Low"].rolling(20).min()

    return out


def latest_snapshot(df: pd.DataFrame) -> dict | None:
    """Extracts the most recent row of indicators as a flat dict for scoring."""
    if df is None or df.empty:
        return None
    row = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else row
    return {
        "close": row.get("Close"),
        "ema20": row.get("EMA20"),
        "ema50": row.get("EMA50"),
        "ema200": row.get("EMA200"),
        "rsi14": row.get("RSI14"),
        "macd": row.get("MACD"),
        "macd_signal": row.get("MACD_signal"),
        "macd_hist": row.get("MACD_hist"),
        "macd_hist_prev": prev.get("MACD_hist"),
        "atr14": row.get("ATR14"),
        "volume": row.get("Volume"),
        "vol_avg20": row.get("VolAvg20"),
        "vol_spike": row.get("VolSpike"),
        "high20": row.get("High20"),
        "low20": row.get("Low20"),
    }
