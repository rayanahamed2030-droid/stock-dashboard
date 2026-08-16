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

from fetch_data import fetch_price_history, fetch_fundamentals, get_symbol_universe
from indicators import compute_indicators, latest_snapshot
from scorer import technical_score, fundamental_score, combined_scores, trade_levels as scorer_trade_levels

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def backtest_symbol(symbol: str, df, fund: dict, threshold: float, hold_days: int,
                     round_trip_cost_pct: float = 0.25,
                     atr_multiplier: float = 3.0, reward_risk: float = 2.0) -> list[dict]:
    """Returns a list of simulated trade outcomes for one symbol.

    round_trip_cost_pct: estimated total cost of entering AND exiting a delivery
    trade in India - brokerage (often near-zero with discount brokers) + STT
    (0.1% on the sell side for delivery) + slippage (the gap between intended
    and actual fill price). 0.25% is a reasonable middle estimate; real costs
    vary by broker and trade size. This is subtracted from every simulated
    trade's return so the backtest reports what you'd ACTUALLY keep, not the
    theoretical price-only return.
    """
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
            levels = scorer_trade_levels(snap, atr_multiplier=atr_multiplier, reward_risk=reward_risk)
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

            gross_pct_return = (exit_price - entry) / entry * 100
            net_pct_return = round(gross_pct_return - round_trip_cost_pct, 2)
            trades.append({
                "symbol": symbol, "entry_idx": i, "swing_score": swing_score,
                "outcome": outcome, "pct_return": net_pct_return,
                "gross_pct_return": round(gross_pct_return, 2),
            })
            i += hold_days  # avoid overlapping trades on the same stock
        else:
            i += 1

    return trades


def run(symbols: list[str], threshold: float, hold_days: int):
    price_data = fetch_price_history(symbols, period="2y")
    all_trades = []
    per_symbol_summary = []

    for symbol in symbols:
        fund = fetch_fundamentals(symbol)
        trades = backtest_symbol(symbol, price_data.get(symbol), fund, threshold, hold_days)
        all_trades.extend(trades)
        per_symbol_summary.append((symbol, len(trades)))
        log.info(f"{symbol}: {len(trades)} simulated trades")

    if not all_trades:
        log.warning("No trades were triggered - try lowering --threshold or check data availability.")
        return

    wins = [t for t in all_trades if t["pct_return"] > 0]
    win_rate = round(len(wins) / len(all_trades) * 100, 1)
    avg_return_net = round(statistics.mean(t["pct_return"] for t in all_trades), 2)
    avg_return_gross = round(statistics.mean(t["gross_pct_return"] for t in all_trades), 2)
    avg_win = round(statistics.mean([t["pct_return"] for t in wins]), 2) if wins else 0
    losses = [t for t in all_trades if t["pct_return"] <= 0]
    avg_loss = round(statistics.mean([t["pct_return"] for t in losses]), 2) if losses else 0
    stocks_with_trades = len([s for s, c in per_symbol_summary if c > 0])

    print("\n===== BACKTEST RESULTS =====")
    print(f"Stocks scanned               : {len(symbols)}")
    print(f"Stocks with >=1 trade         : {stocks_with_trades}")
    print(f"Total simulated trades       : {len(all_trades)}")
    print(f"Win rate                     : {win_rate}%")
    print(f"Avg return/trade (GROSS)     : {avg_return_gross}%  <- price movement only")
    print(f"Avg return/trade (NET)       : {avg_return_net}%  <- after ~0.25% round-trip costs")
    print(f"Average winner (net)         : {avg_win}%")
    print(f"Average loser (net)          : {avg_loss}%")
    print("=============================")
    print("Reminder: this is a heuristic backtest with static fundamentals held")
    print("constant across the window. Treat it as directional, not definitive.")
    print("NET figures assume a 0.25% round-trip cost estimate (brokerage+STT+slippage) -")
    print("your actual broker's costs may differ; check your real cost structure.")
    if len(symbols) < 30:
        print("\nNOTE: small sample size - results may not generalize. Run with")
        print("--universe nifty500 (or a larger --max-stocks) for a more reliable read.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", type=str, default=None,
                         help="Comma-separated NSE symbols, e.g. RELIANCE,TCS,INFY")
    parser.add_argument("--universe", type=str, choices=["nifty500", "full"], default=None,
                         help="Instead of --symbols, backtest across a whole universe "
                              "(same source as the daily scan)")
    parser.add_argument("--max-stocks", type=int, default=None,
                         help="Optional cap on how many stocks to backtest from --universe "
                              "(useful to keep runtime reasonable, e.g. 100)")
    parser.add_argument("--threshold", type=float, default=75.0,
                         help="Minimum swing_score to trigger a simulated trade")
    parser.add_argument("--hold-days", type=int, default=10,
                         help="Max days to hold before timing out the trade")
    args = parser.parse_args()

    if args.universe:
        symbol_list = get_symbol_universe(args.universe)
        if args.max_stocks:
            symbol_list = symbol_list[: args.max_stocks]
        log.info(f"Backtesting {len(symbol_list)} stocks from {args.universe} universe")
    elif args.symbols:
        symbol_list = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        parser.error("Provide either --symbols or --universe")

    run(symbol_list, args.threshold, args.hold_days)
