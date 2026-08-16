"""
main.py
Daily entry point: fetches data for the chosen universe, scores every stock,
and writes out the top N swing picks and top N intraday picks as JSON,
consumed by the static dashboard.

Usage:
    python main.py --universe nifty500 --top 10
    python main.py --universe full --top 10       # slower, full NSE (~2000 stocks)

IMPORTANT (read before trusting the output):
This produces a RANKED, RULE-BASED SCORE - not a prediction of profit and
not remotely close to "99% accurate." Treat picks as a shortlist to research
further, not as trade signals to act on blindly. Always use your own risk
management (position sizing, stop-loss) regardless of the score shown.
"""

import argparse
import json
import datetime
import logging
from pathlib import Path

from fetch_data import get_symbol_universe, fetch_price_history, fetch_fundamentals, fetch_index_history
from indicators import compute_indicators, latest_snapshot, market_regime
from scorer import technical_score, intraday_technical_score, fundamental_score, combined_scores, trade_levels
from sectors import get_sector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"


def select_recommended(swing_picks: list, max_picks: int = 2, min_score: float = 70.0) -> list:
    """
    Narrows the full swing pick list down to the 1-2 the dashboard flags as
    'Recommended', using the same filter a careful trader should apply manually:
      1. Score >= min_score (matches the 65+ threshold that backtested with a
         real edge - 70 leaves some margin above that)
      2. Reasoning is "complete" - has multiple technical reasons AND at least
         some usable fundamental data, not just a technical-only score
      3. Sector diversity - won't recommend two picks from the same sector
      4. Highest score wins each sector slot

    Returns a list of symbols (strings) to flag as recommended=True in the output.
    """
    candidates = [
        p for p in swing_picks
        if p["swing_score"] >= min_score
        and len(p["reasons"].get("technical", [])) >= 3
        and p["fundamental_score"] > 0
    ]

    recommended = []
    used_sectors = set()
    for pick in candidates:  # already sorted by score descending
        sector = get_sector(pick["symbol"])
        if sector != "Unknown" and sector in used_sectors:
            continue  # skip - already have a pick from this sector
        recommended.append(pick["symbol"])
        if sector != "Unknown":
            used_sectors.add(sector)
        if len(recommended) >= max_picks:
            break

    return recommended


def run(universe: str, top_n: int, min_price: float, min_avg_volume: float):
    log.info("Checking overall market regime (Nifty 50)...")
    try:
        index_df = fetch_index_history("^NSEI")
        regime = market_regime(index_df)
    except Exception as e:
        # The market regime check is a nice-to-have, not core to the scan -
        # if it fails for any reason, log it and keep going rather than
        # taking down the entire daily scan.
        log.warning(f"Market regime check failed, continuing without it: {e}")
        regime = {"status": "unknown", "note": "market regime check failed - see logs"}
    log.info(f"Market regime: {regime['status']} - {regime['note']}")

    symbols = get_symbol_universe(universe)
    price_data = fetch_price_history(symbols)

    results = []
    for symbol, df in price_data.items():
        enriched = compute_indicators(df)
        snap = latest_snapshot(enriched)
        if not snap or not snap.get("close"):
            continue

        # basic liquidity/penny-stock filter - adjust to taste
        if snap["close"] < min_price:
            continue
        if snap.get("vol_avg20") and snap["vol_avg20"] < min_avg_volume:
            continue

        tscore, treasons = technical_score(snap)
        itscore, itreasons = intraday_technical_score(snap)

        fund = fetch_fundamentals(symbol)
        fscore, freasons = fundamental_score(fund)

        combo = combined_scores(tscore, treasons, fscore, freasons, itscore, itreasons)
        combo["symbol"] = symbol
        combo["close"] = round(snap["close"], 2)
        combo["atr14"] = round(snap["atr14"], 2) if snap.get("atr14") else None
        combo["trade_levels"] = trade_levels(snap)
        results.append(combo)

    swing_picks = sorted(results, key=lambda x: x["swing_score"], reverse=True)[:top_n]
    intraday_picks = sorted(results, key=lambda x: x["intraday_score"], reverse=True)[:top_n]

    recommended_symbols = select_recommended(swing_picks)
    for pick in swing_picks:
        pick["recommended"] = pick["symbol"] in recommended_symbols
        pick["sector"] = get_sector(pick["symbol"])

    output = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "universe": universe,
        "universe_size_scanned": len(results),
        "market_regime": regime,
        "disclaimer": (
            "Scores are a rule-based ranking of technical/fundamental setup strength, "
            "not a prediction or guarantee of profit. Always apply your own risk management."
        ),
        "recommended_note": (
            "'Recommended' picks passed an extra filter: score >= 70, complete "
            "technical + fundamental reasoning, and sector diversity across the "
            "recommended set. Still not a guarantee - do your own review."
        ),
        "swing_picks": swing_picks,
        "intraday_picks": intraday_picks,
    }

    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / "daily_picks.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    log.info(f"Scanned {len(results)} stocks. Wrote picks to {out_path}")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", choices=["nifty500", "full"], default="nifty500")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--min-price", type=float, default=20.0,
                         help="Filter out stocks below this price (avoid illiquid penny stocks)")
    parser.add_argument("--min-avg-volume", type=float, default=50000,
                         help="Filter out stocks below this 20-day average volume")
    args = parser.parse_args()

    run(args.universe, args.top, args.min_price, args.min_avg_volume)
