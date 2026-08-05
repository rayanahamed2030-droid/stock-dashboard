"""
fetch_data.py
Fetches the NSE stock universe (symbol list) and price/fundamental data.

Data sources:
- Symbol list: NSE official archives (CSV) - Nifty 500 index constituents or full equity list.
- Price history + fundamentals: yfinance (Yahoo Finance), using ".NS" suffix for NSE tickers.

NOTE: yfinance fundamental coverage for Indian small/micro-cap stocks is inconsistent.
Stocks with missing fundamental data are still included with a partial score (technical-only)
rather than dropped, so the pipeline doesn't silently shrink the universe.
"""

import io
import time
import logging
import requests
import pandas as pd
import yfinance as yf
from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

NIFTY500_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
FULL_EQUITY_URL = "https://nsearchives.nseindia.com/content/equity/EQUITY_L.csv"

NSE_HEADERS = {
    # NSE blocks default requests without a browser-like User-Agent
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/csv,*/*",
}


def get_symbol_universe(universe: str = "nifty500") -> list[str]:
    """
    Returns a list of NSE trading symbols (without .NS suffix).
    universe: "nifty500" (default, faster) or "full" (all NSE equities, slower).
    """
    url = FULL_EQUITY_URL if universe == "full" else NIFTY500_URL
    log.info(f"Fetching symbol universe ({universe}) from {url}")
    resp = requests.get(url, headers=NSE_HEADERS, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    symbol_col = "Symbol" if "Symbol" in df.columns else df.columns[0]
    symbols = df[symbol_col].dropna().astype(str).str.strip().tolist()
    log.info(f"Loaded {len(symbols)} symbols")
    return symbols


def fetch_price_history(symbols: list[str], period: str = "9mo", batch_size: int = 50,
                         pause_sec: float = 1.5) -> dict[str, pd.DataFrame]:
    """
    Downloads daily OHLCV history for each symbol via yfinance, in batches to avoid
    rate limiting. Returns dict of symbol -> DataFrame (empty DataFrame if fetch failed).
    """
    results: dict[str, pd.DataFrame] = {}
    tickers = [f"{s}.NS" for s in symbols]

    for i in tqdm(range(0, len(tickers), batch_size), desc="Fetching price history"):
        batch = tickers[i:i + batch_size]
        try:
            data = yf.download(
                batch, period=period, interval="1d", group_by="ticker",
                threads=True, progress=False, auto_adjust=True,
            )
        except Exception as e:
            log.warning(f"Batch fetch failed ({batch[:3]}...): {e}")
            data = None

        for ticker in batch:
            symbol = ticker.replace(".NS", "")
            try:
                if len(batch) == 1:
                    df = data
                else:
                    df = data[ticker] if data is not None and ticker in data else pd.DataFrame()
                df = df.dropna(how="all")
                results[symbol] = df
            except Exception:
                results[symbol] = pd.DataFrame()

        time.sleep(pause_sec)  # be polite to the API

    return results


def fetch_fundamentals(symbol: str) -> dict:
    """
    Fetches key fundamental ratios for a single symbol via yfinance.
    Returns a dict with None values for any field that isn't available.
    """
    fields = {
        "pe_ratio": None, "peg_ratio": None, "pb_ratio": None,
        "debt_to_equity": None, "roe": None,
        "revenue_growth": None, "earnings_growth": None,
        "profit_margin": None, "market_cap": None,
    }
    try:
        info = yf.Ticker(f"{symbol}.NS").info
        fields["pe_ratio"] = info.get("trailingPE")
        fields["peg_ratio"] = info.get("pegRatio")
        fields["pb_ratio"] = info.get("priceToBook")
        fields["debt_to_equity"] = info.get("debtToEquity")
        fields["roe"] = info.get("returnOnEquity")
        fields["revenue_growth"] = info.get("revenueGrowth")
        fields["earnings_growth"] = info.get("earningsGrowth")
        fields["profit_margin"] = info.get("profitMargins")
        fields["market_cap"] = info.get("marketCap")
    except Exception as e:
        log.debug(f"Fundamentals fetch failed for {symbol}: {e}")
    return fields
