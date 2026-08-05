"""
backtest.py
Walks through a stock's price history day-by-day, re-computes the swing score
AS IT WOULD HAVE BEEN on that day (no lookahead), and simulates what would have
happened if a trade was taken whenever the score crossed a threshold.

This is what turns "we think this scoring logic works" into an actual measured
number - the thing most AI stock-picker tools conveniently don't show you.

Usage:
    python backtest.py --symbols RELIANCE,TCS,INFY --threshold 65 --hold-days 10

Limitations (important):
- Fundamentals are fetched once (current values) and held constant across the
  backtest window, since point-in-time historical fundamentals aren't available
  via yfinance. This means fundamental scoring in the backtest is an approximation -
  technical scoring is the reliable part of this backtest.
- Past performance of a rule set does not guarantee future performance. Markets
  change regimes. Treat this as a sanity check, not a guarantee.
"""

import argparse
import statistics
import logging

from fetch_data import fetch_price_history, fetch_fundamentals
from indicators import compute_indicators, latest_snapshot
from scorer import technical_score, fundamental_score, combined_scores, trade_levels

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def backtest_symbol(symbol: str, df, fund: dict, threshold: float, hold_days: int) -> list[dict]:
    """Returns a list of simulated trade outcomes for one symbol."""
    enriched = compute_indicators(df)
    if enriched.empty or len(enriched) < 220:
        return []

    fscore, _ = fundamental_score(fund)
    trades = []
    i = 200  # need enough history for EMA200 to be valid

    while i < len(enriched) - hold_days:
        window = enriched.iloc[: i + 1]  # only data UP TO day i - no lookahead
        snap = latest_snapshot(window)
        if not snap or not snap.get("close"):
            i += 1
            continue

        tscore, _ = technical_score(snap)
        combo = combined_scores(tscore, [], fscore, [])
        swing_score = combo["swing_score"]

        if swing_score >= threshold:
            levels = trade_levels(snap)
            if levels["entry"] is None:
                i += 1
                continue

            entry = levels["entry"]
            stop = levels["stop_loss"]
            target = levels["target"]

            outcome = "timeout"
            exit_price = enriched.iloc[i + hold_days]["Close"]

            for j in range(i + 1, min(i + 1 + hold_days, len(enriched))):
                day_high = enriched.iloc[j]["High"]
                day_low = enriched.iloc[j]["Low"]
                if day_low <= stop:
                    outcome = "stop_loss"
                    exit_price = stop
                    break
                if day_high >= target:
                    outcome = "target"
                    exit_price = target
                    break

            pct_return = round((exit_price - entry) / entry * 100, 2)
            trades.append({
                "symbol": symbol, "entry_idx": i, "swing_score": swing_score,
                "outcome": outcome, "pct_return": pct_return,
            })
            i += hold_days  # avoid overlapping trades on the same stock
        else:
            i += 1

    return trades


def run(symbols: list[str], threshold: float, hold_days: int):
    price_data = fetch_price_history(symbols, period="2y")
    all_trades = []

    for symbol in symbols:
        fund = fetch_fundamentals(symbol)
        trades = backtest_symbol(symbol, price_data.get(symbol), fund, threshold, hold_days)
        all_trades.extend(trades)
        log.info(f"{symbol}: {len(trades)} simulated trades")

    if not all_trades:
        log.warning("No trades were triggered - try lowering --threshold or check data availability.")
        return

    wins = [t for t in all_trades if t["pct_return"] > 0]
    win_rate = round(len(wins) / len(all_trades) * 100, 1)
    avg_return = round(statistics.mean(t["pct_return"] for t in all_trades), 2)
    avg_win = round(statistics.mean([t["pct_return"] for t in wins]), 2) if wins else 0
    losses = [t for t in all_trades if t["pct_return"] <= 0]
    avg_loss = round(statistics.mean([t["pct_return"] for t in losses]), 2) if losses else 0

    print("\n===== BACKTEST RESULTS =====")
    print(f"Total simulated trades : {len(all_trades)}")
    print(f"Win rate               : {win_rate}%")
    print(f"Average return/trade   : {avg_return}%")
    print(f"Average winner         : {avg_win}%")
    print(f"Average loser          : {avg_loss}%")
    print("=============================")
    print("Reminder: this is a heuristic backtest with static fundamentals held")
    print("constant across the window. Treat it as directional, not definitive.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", type=str, required=True,
                         help="Comma-separated NSE symbols, e.g. RELIANCE,TCS,INFY")
    parser.add_argument("--threshold", type=float, default=65.0,
                         help="Minimum swing_score to trigger a simulated trade")
    parser.add_argument("--hold-days", type=int, default=10,
                         help="Max days to hold before timing out the trade")
    args = parser.parse_args()

    run([s.strip().upper() for s in args.symbols.split(",")], args.threshold, args.hold_days)
