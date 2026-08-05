"""
scorer.py
Turns raw technical + fundamental data into transparent 0-100 scores
with human-readable reasoning, for two separate strategies:

  - Swing score: blends technical setup with fundamental quality
                 (swing trades run days-to-weeks, fundamentals matter more)
  - Intraday score: weighted almost entirely toward momentum/volume/volatility
                 (fundamentals barely matter over a single session)

IMPORTANT: These are rule-based heuristic scores, not accuracy guarantees.
They rank *how well a stock currently matches a favorable technical/fundamental
setup*, not a probability of profit.
"""


def _safe(val, default=0):
    return val if val is not None and val == val else default  # val==val filters NaN


def technical_score(snap: dict) -> tuple[float, list[str]]:
    """Returns (score 0-100, list of reasoning tags) from a technical snapshot."""
    if not snap:
        return 0.0, ["no price data"]

    score = 0.0
    reasons = []
    close = _safe(snap.get("close"))
    ema20 = _safe(snap.get("ema20"))
    ema50 = _safe(snap.get("ema50"))
    ema200 = snap.get("ema200")
    rsi = _safe(snap.get("rsi14"), 50)
    macd_hist = _safe(snap.get("macd_hist"))
    macd_hist_prev = _safe(snap.get("macd_hist_prev"))
    vol_spike = _safe(snap.get("vol_spike"), 1)
    high20 = _safe(snap.get("high20"))

    # Trend (35 pts)
    if close > ema20 > ema50:
        score += 25
        reasons.append("price above EMA20 & EMA50 (uptrend)")
    elif close > ema20:
        score += 12
        reasons.append("price above EMA20")
    if ema200 and close > ema200:
        score += 10
        reasons.append("above 200 EMA (long-term uptrend)")

    # Momentum (30 pts)
    if 50 < rsi < 70:
        score += 20
        reasons.append(f"RSI {rsi:.0f} - healthy bullish momentum")
    elif rsi >= 70:
        score += 8
        reasons.append(f"RSI {rsi:.0f} - overbought, momentum strong but stretched")
    elif 40 < rsi <= 50:
        score += 8
        reasons.append(f"RSI {rsi:.0f} - neutral")

    if macd_hist > 0 and macd_hist > macd_hist_prev:
        score += 10
        reasons.append("MACD histogram rising above zero (bullish momentum building)")
    elif macd_hist > 0:
        score += 5
        reasons.append("MACD histogram positive")

    # Volume confirmation (20 pts)
    if vol_spike >= 1.5:
        score += 20
        reasons.append(f"volume {vol_spike:.1f}x 20-day average (strong interest)")
    elif vol_spike >= 1.1:
        score += 10
        reasons.append(f"volume {vol_spike:.1f}x average (mild pickup)")

    # Breakout proximity (15 pts)
    if high20 and close >= high20 * 0.98:
        score += 15
        reasons.append("near/at 20-day high (breakout zone)")

    return min(score, 100.0), reasons


def fundamental_score(fund: dict) -> tuple[float, list[str]]:
    """Returns (score 0-100, list of reasoning tags) from fundamental data.
    Missing fields are simply skipped (not penalized), since coverage is patchy."""
    if not fund:
        return 0.0, ["no fundamental data"]

    score = 0.0
    max_possible = 0.0
    reasons = []

    pe = fund.get("pe_ratio")
    if pe is not None:
        max_possible += 20
        if 0 < pe < 30:
            score += 20
            reasons.append(f"P/E {pe:.1f} - reasonable valuation")
        elif 30 <= pe < 50:
            score += 8
            reasons.append(f"P/E {pe:.1f} - moderately expensive")

    roe = fund.get("roe")
    if roe is not None:
        max_possible += 25
        if roe > 0.15:
            score += 25
            reasons.append(f"ROE {roe*100:.1f}% - strong returns on equity")
        elif roe > 0.08:
            score += 12
            reasons.append(f"ROE {roe*100:.1f}% - moderate")

    de = fund.get("debt_to_equity")
    if de is not None:
        max_possible += 20
        if de < 50:
            score += 20
            reasons.append(f"D/E {de:.0f} - low debt")
        elif de < 100:
            score += 10
            reasons.append(f"D/E {de:.0f} - manageable debt")

    rev_growth = fund.get("revenue_growth")
    if rev_growth is not None:
        max_possible += 20
        if rev_growth > 0.15:
            score += 20
            reasons.append(f"revenue growth {rev_growth*100:.1f}% YoY - strong")
        elif rev_growth > 0.05:
            score += 10
            reasons.append(f"revenue growth {rev_growth*100:.1f}% YoY - moderate")

    earn_growth = fund.get("earnings_growth")
    if earn_growth is not None:
        max_possible += 15
        if earn_growth > 0.15:
            score += 15
            reasons.append(f"earnings growth {earn_growth*100:.1f}% YoY - strong")
        elif earn_growth > 0:
            score += 7
            reasons.append(f"earnings growth {earn_growth*100:.1f}% YoY - positive")

    if max_possible == 0:
        return 0.0, ["no usable fundamental fields"]

    # Normalize to 0-100 based on how many fields were actually available
    normalized = (score / max_possible) * 100
    return round(normalized, 1), reasons


def trade_levels(snap: dict, atr_multiplier: float = 1.75, reward_risk: float = 2.0) -> dict:
    """
    Computes rule-based entry, stop-loss, and target levels from the technical
    snapshot, using ATR (Average True Range) for volatility-adjusted risk sizing.
    This is the same standard approach professional swing traders use manually -
    not a prediction of where price will go, just a defined risk/reward structure.

    entry:      current close (or breakout level if near 20-day high)
    stop_loss:  entry - (ATR x multiplier)  -> where the trade idea is invalidated
    target:     entry + (risk x reward_risk) -> where profit is booked
    """
    close = snap.get("close")
    atr = snap.get("atr14")
    high20 = snap.get("high20")

    if not close or not atr or atr <= 0:
        return {"entry": None, "stop_loss": None, "target": None, "risk_per_share": None,
                "reward_risk_ratio": None, "note": "insufficient data for trade levels"}

    # If price is already near a breakout zone, entry is the breakout level;
    # otherwise use current close as the reference entry.
    entry = high20 if (high20 and close >= high20 * 0.98) else close

    risk_per_share = round(atr * atr_multiplier, 2)
    stop_loss = round(entry - risk_per_share, 2)
    target = round(entry + risk_per_share * reward_risk, 2)

    return {
        "entry": round(entry, 2),
        "stop_loss": stop_loss,
        "target": target,
        "risk_per_share": risk_per_share,
        "reward_risk_ratio": reward_risk,
        "note": f"Stop = {atr_multiplier}x ATR below entry, target = {reward_risk}:1 reward/risk",
    }


def combined_scores(tech_score: float, tech_reasons: list, fund_score: float,
                     fund_reasons: list) -> dict:
    """Produces both swing and intraday composite scores with reasoning."""
    swing = round(0.55 * tech_score + 0.45 * fund_score, 1)
    intraday = round(0.90 * tech_score + 0.10 * fund_score, 1)

    return {
        "swing_score": swing,
        "intraday_score": intraday,
        "technical_score": round(tech_score, 1),
        "fundamental_score": round(fund_score, 1),
        "reasons": {
            "technical": tech_reasons,
            "fundamental": fund_reasons,
        },
    }
