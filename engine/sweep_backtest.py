"""
sweep_backtest.py
Searches for better threshold/stop/target parameters WITHOUT overfitting:
splits the stock universe into a TRAIN set (used to search) and a TEST set
(checked only ONCE, at the end, with whatever settings won on train).

This is the responsible way to answer "can we get a better win rate" - tuning
parameters against the same data you then report results on is how the 55%
figure from the small sample turned out to be an illusion. A real edge has to
survive being checked on stocks the search never touched.

Usage:
    python sweep_backtest.py --universe nifty500 --max-stocks 100 --hold-days 10

Output: the best-performing parameter combination on TRAIN data, then that
same combination's honest performance on TEST data (the number that actually
matters). If train looks great but test doesn't, that combination was
overfit - don't trust it just because train looked good.
"""

import argparse
import logging
import random
import statistics

from fetch_data import fetch_price_history, fetch_fundamentals, get_symbol_universe
from backtest import backtest_symbol

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

THRESHOLDS = [60, 65, 70, 75]
ATR_MULTIPLIERS = [1.75, 2.0, 2.5, 3.0]
REWARD_RISK_RATIOS = [1.0, 1.5, 2.0]

MIN_TRADES_FOR_CONSIDERATION = 30


def evaluate(symbols: list[str], price_data: dict, fund_cache: dict,
             threshold: float, hold_days: int, atr_mult: float, reward_risk: float) -> dict:
    """Runs backtest_symbol across a set of stocks for one parameter combo,
    returns aggregate stats."""
    all_trades = []
    for symbol in symbols:
        trades = backtest_symbol(
            symbol, price_data.get(symbol), fund_cache.get(symbol, {}),
            threshold, hold_days, atr_multiplier=atr_mult, reward_risk=reward_risk,
        )
        all_trades.extend(trades)

    all_trades = [t for t in all_trades if t["pct_return"] == t["pct_return"]]  # NaN != NaN

    if len(all_trades) < MIN_TRADES_FOR_CONSIDERATION:
        return {"n_trades": len(all_trades), "win_rate": None, "avg_return": None}

    wins = [t for t in all_trades if t["pct_return"] > 0]
    win_rate = round(len(wins) / len(all_trades) * 100, 1)
    avg_return = round(statistics.mean(t["pct_return"] for t in all_trades), 3)
    return {"n_trades": len(all_trades), "win_rate": win_rate, "avg_return": avg_return}


def run(universe: str, max_stocks: int, hold_days: int, train_frac: float = 0.7, seed: int = 42):
    symbols = get_symbol_universe(universe)
    if max_stocks:
        symbols = symbols[:max_stocks]

    random.Random(seed).shuffle(symbols)
    split_idx = int(len(symbols) * train_frac)
    train_symbols = symbols[:split_idx]
    test_symbols = symbols[split_idx:]
    log.info(f"Train set: {len(train_symbols)} stocks | Test set: {len(test_symbols)} stocks")

    log.info("Fetching price history for all stocks (one-time)...")
    price_data = fetch_price_history(symbols, period="2y")
    log.info("Fetching fundamentals for all stocks (one-time)...")
    fund_cache = {s: fetch_fundamentals(s) for s in symbols}

    log.info(f"Searching {len(THRESHOLDS) * len(ATR_MULTIPLIERS) * len(REWARD_RISK_RATIOS)} "
              f"parameter combinations on TRAIN set only...")

    results = []
    for threshold in THRESHOLDS:
        for atr_mult in ATR_MULTIPLIERS:
            for rr in REWARD_RISK_RATIOS:
                stats = evaluate(train_symbols, price_data, fund_cache, threshold, hold_days, atr_mult, rr)
                if stats["avg_return"] is not None:
                    results.append({
                        "threshold": threshold, "atr_multiplier": atr_mult, "reward_risk": rr,
                        **stats,
                    })
                log.info(f"  threshold={threshold} atr={atr_mult} rr={rr} -> "
                         f"{stats['n_trades']} trades, "
                         f"{stats['win_rate']}% win, {stats['avg_return']}% avg return")

    if not results:
        log.warning("No parameter combination produced enough trades to evaluate. "
                     "Try a larger --max-stocks or lower MIN_TRADES_FOR_CONSIDERATION.")
        return

    results.sort(key=lambda r: r["avg_return"], reverse=True)
    best = results[0]

    print("\n===== BEST ON TRAIN SET =====")
    print(f"threshold={best['threshold']}  atr_multiplier={best['atr_multiplier']}  "
          f"reward_risk={best['reward_risk']}")
    print(f"Train trades: {best['n_trades']} | Win rate: {best['win_rate']}% | "
          f"Avg return: {best['avg_return']}%")

    print("\nTop 5 combinations on TRAIN (for context):")
    for r in results[:5]:
        print(f"  threshold={r['threshold']:.0f} atr={r['atr_multiplier']} rr={r['reward_risk']} "
              f"-> {r['n_trades']} trades, {r['win_rate']}% win, {r['avg_return']}% avg return")

    log.info("\nChecking best-on-train parameters against TEST set (unseen data)...")
    test_stats = evaluate(test_symbols, price_data, fund_cache,
                            best["threshold"], hold_days, best["atr_multiplier"], best["reward_risk"])

    print("\n===== SAME PARAMETERS ON TEST SET (the number that matters) =====")
    print(f"Test trades: {test_stats['n_trades']} | Win rate: {test_stats['win_rate']}% | "
          f"Avg return: {test_stats['avg_return']}%")
    print("=====================================================================")

    if test_stats["avg_return"] is None:
        print("Not enough test trades to draw a conclusion - try a larger --max-stocks.")
    elif test_stats["avg_return"] > 0 and best["avg_return"] > 0:
        gap = best["avg_return"] - test_stats["avg_return"]
        print(f"\nBoth train and test are positive. Train-to-test gap: {gap:.3f} percentage points.")
        print("A small gap is a good sign the edge is real, not just overfit to train data.")
        print("A large gap means treat this with caution even though test is still positive.")
    else:
        print("\nTest set result is NOT positive even though train looked good.")
        print("This is a classic overfitting signal - do NOT trust the train-set number.")
        print("Honest conclusion: this parameter combination does not have a real edge yet.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", type=str, choices=["nifty500", "full"], default="nifty500")
    parser.add_argument("--max-stocks", type=int, default=100)
    parser.add_argument("--hold-days", type=int, default=10)
    parser.add_argument("--train-frac", type=float, default=0.7,
                         help="Fraction of stocks used for searching (rest held out for testing)")
    parser.add_argument("--seed", type=int, default=42,
                         help="Random seed for the train/test split - run with different seeds "
                              "to check whether results are stable, not a one-off lucky split")
    args = parser.parse_args()

    run(args.universe, args.max_stocks, args.hold_days, args.train_frac, args.seed)
