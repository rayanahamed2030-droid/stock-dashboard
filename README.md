# NSE Swing & Intraday Scanner

A daily, rule-based scoring dashboard for NSE stocks — combines technical setup
(trend, momentum, volume, breakout proximity) and fundamentals (P/E, ROE, debt,
growth) into two ranked lists: **swing picks** and **intraday picks**.

**Important:** this is a transparent heuristic scorer, not a prediction engine.
No system predicts stock moves with 99% accuracy — treat the output as a
shortlist to research further, and always use your own stop-loss/position sizing.

## How it works

```
engine/fetch_data.py   → pulls NSE symbol list + price history + fundamentals
engine/indicators.py   → computes EMA/RSI/MACD/ATR/volume indicators
engine/scorer.py       → turns indicators + fundamentals into 0-100 scores + reasons
engine/main.py         → orchestrates the scan, writes data/daily_picks.json
dashboard/index.html   → static page that reads data/daily_picks.json and displays picks
.github/workflows/     → GitHub Action that runs main.py daily after market close
```

## Setup (one-time)

1. **Create a GitHub repo** and push this folder to it.
2. **Enable GitHub Pages** (Settings → Pages → deploy from `main` branch, `/dashboard` isn't
   directly supported by Pages root config, so easiest is to also copy `dashboard/index.html`
   to the repo root, or use a `docs/` folder — see "Hosting" below).
3. No API keys needed for the MVP — yfinance and the NSE archive CSVs are public.
   If you later switch to Kite Connect or another paid API, add credentials as
   **GitHub Secrets** (Settings → Secrets and variables → Actions) and reference them
   in the workflow as `${{ secrets.YOUR_KEY }}`.
4. The GitHub Action (`.github/workflows/daily-scan.yml`) runs automatically at
   4:45 PM IST on weekdays and commits the updated `data/daily_picks.json` — no server needed.

## Hosting the dashboard

Simplest options, in order of how little setup they need:
- **GitHub Pages**: put `dashboard/index.html` and `data/` at repo root (or a `docs/` folder),
  enable Pages in repo settings. Free, zero config.
- **Firebase Hosting**: same pattern you used for the Task Dashboard —
  `firebase init hosting`, deploy the `dashboard/` + `data/` folders.

## Running locally (to test before automating)

```bash
cd engine
pip install -r requirements.txt --break-system-packages
python main.py --universe nifty500 --top 10
```

This writes `data/daily_picks.json`. Then open `dashboard/index.html` in a browser
(or serve it: `python -m http.server` from the repo root) to view it.

## Scaling to full NSE

`python main.py --universe full --top 10` scans all ~2000 NSE-listed equities instead
of just the Nifty 500. It's slower (yfinance rate limits mean this can take well over
an hour) and fundamental data quality drops for micro-caps. Recommend starting with
Nifty 500 and only switching to `full` once you've validated the picks make sense.

## Entry / stop-loss / target levels

Each pick now includes rule-based trade levels (`engine/scorer.py: trade_levels()`):
- **Entry**: current close, or the 20-day-high breakout level if price is near it
- **Stop-loss**: entry minus 1.75x ATR(14) — adapts to each stock's own volatility
- **Target**: entry plus (risk x 2), i.e. a 2:1 reward-to-risk setup

This is standard swing-trading risk management, not a prediction. The point is a
*defined, consistent* risk/reward per trade — you can be right less than half
the time and still be profitable if winners are sized bigger than losers.

## Backtesting (measuring real accuracy)

```bash
cd engine
python backtest.py --symbols RELIANCE,TCS,INFY,HDFCBANK --threshold 65 --hold-days 10
```

This walks through 2 years of history day-by-day, re-computes the swing score
using only data available up to that day (no lookahead), and simulates what
would have happened if a trade was taken whenever the score crossed the
threshold. It reports real win rate and average return — this is the honest
number to look at instead of trusting the scoring logic blindly. Run this
before committing real capital, and re-run periodically since market regimes
change.

Known limitation: fundamentals are held constant across the backtest window
(point-in-time historical fundamentals aren't available via yfinance), so the
backtest is most reliable as a read on the *technical* scoring rules.

## Tuning the scoring logic

All scoring weights and thresholds live in `engine/scorer.py` — e.g. how much RSI,
volume spikes, or ROE matter. Adjust `min_price` / `min_avg_volume` in `main.py`
to filter out illiquid or penny stocks.

## Known limitations (read before relying on this)

- **Fundamental data coverage is patchy** for small/micro-cap Indian stocks via yfinance.
  Stocks with missing fundamentals still appear (technical-only score) rather than
  being silently dropped.
- **"Intraday" picks here are based on the previous day's close**, not live intraday
  price action — genuinely live intraday signals would need real-time data (e.g. Kite
  Connect websocket), which is a bigger build. Treat these as "stocks worth watching
  at tomorrow's open," not live intraday alerts.
- **No backtesting yet.** The scoring weights are reasonable heuristics, not
  validated against historical performance. Worth backtesting before trading on it.
- **No accuracy tracking yet.** Consider adding a simple log that records each day's
  picks + next-day/next-week return, so you can actually measure how the scores perform
  over time rather than trusting them blindly.
