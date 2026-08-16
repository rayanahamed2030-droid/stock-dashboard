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
    """Returns (score 0-100, list of reasoning tags) from a technical snapshot.
    This is the SWING-oriented technical score - PULLBACK-TO-SUPPORT style:
    rewards stocks in a confirmed uptrend that have cooled off toward their
    EMA20 (a classic swing-trading entry), rather than chasing strength at
    a fresh breakout high. Backtesting showed breakout-chasing entries got
    stopped out too often on large-caps; pullback entries buy temporary
    weakness in an already-proven trend instead of paying up for a stock
    that just ran."""
    if not snap:
        return 0.0, ["no price data"]

    score = 0.0
    reasons = []
    close = _safe(snap.get("close"))
    ema20 = _safe(snap.get("ema20"))
    ema50 = _safe(snap.get("ema50"))
    ema200 = snap.get("ema200")
    ema200_20d_ago = snap.get("ema200_20d_ago")
    high252 = snap.get("high252")
    rsi = _safe(snap.get("rsi14"), 50)
    macd_hist = _safe(snap.get("macd_hist"))
    macd_hist_prev = _safe(snap.get("macd_hist_prev"))

    if close > ema50:
        score += 10
        reasons.append("price above EMA50 (established uptrend)")
    if ema200 and ema50 > ema200:
        score += 10
        reasons.append("EMA50 above EMA200 (longer-term uptrend intact)")

    if ema200 and ema200_20d_ago and ema200_20d_ago > 0:
        if ema200 > ema200_20d_ago:
            score += 15
            reasons.append("200-day average sloping upward (genuine long-term uptrend)")

    if high252 and high252 > 0 and close >= high252 * 0.75:
        score += 10
        reasons.append("within 25% of 52-week high (market leadership)")

    if ema20 > 0:
        dist_pct = abs(close - ema20) / ema20 * 100
        if dist_pct <= 2.0 and close >= ema20 * 0.97:
            score += 25
            reasons.append(f"price pulled back to EMA20 support ({dist_pct:.1f}% away)")
        elif dist_pct <= 4.0 and close >= ema20 * 0.95:
            score += 13
            reasons.append(f"price near EMA20 support ({dist_pct:.1f}% away)")

    if 35 <= rsi <= 55:
        score += 20
        reasons.append(f"RSI {rsi:.0f} - momentum reset, room to run")
    elif 55 < rsi <= 65:
        score += 10
        reasons.append(f"RSI {rsi:.0f} - mild pullback in momentum")

    if macd_hist > 0:
        score += 10
        reasons.append("MACD histogram still positive through the pullback")
    elif macd_hist > macd_hist_prev:
        score += 5
        reasons.append("MACD histogram turning back up")

    return min(score, 100.0), reasons


def intraday_technical_score(snap: dict) -> tuple[float, list[str]]:
    """Returns (score 0-100, list of reasoning tags) tuned for INTRADAY setups.
    Unlike the swing score, this deliberately rewards volume surges, volatility
    relative to price, and momentum acceleration - the things that matter for a
    single session - and does NOT require an established multi-week trend
    (a stock can be a great intraday mover without being above its 200 EMA).
    This is what keeps the intraday list genuinely different from the swing list."""
    if not snap:
        return 0.0, ["no price data"]

    score = 0.0
    reasons = []
    close = _safe(snap.get("close"))
    atr = _safe(snap.get("atr14"))
    rsi = _safe(snap.get("rsi14"), 50)
    macd_hist = _safe(snap.get("macd_hist"))
    macd_hist_prev = _safe(snap.get("macd_hist_prev"))
    vol_spike = _safe(snap.get("vol_spike"), 1)
    high20 = _safe(snap.get("high20"))
    low20 = _safe(snap.get("low20"))

    if vol_spike >= 3.0:
        score += 40
        reasons.append(f"volume {vol_spike:.1f}x average - very high intraday interest")
    elif vol_spike >= 2.0:
        score += 28
        reasons.append(f"volume {vol_spike:.1f}x average - strong intraday interest")
    elif vol_spike >= 1.3:
        score += 14
        reasons.append(f"volume {vol_spike:.1f}x average - moderate pickup")

    if close > 0 and atr > 0:
        atr_pct = (atr / close) * 100
        if atr_pct >= 3.0:
            score += 25
            reasons.append(f"ATR {atr_pct:.1f}% of price - high volatility, good intraday range")
        elif atr_pct >= 1.8:
            score += 15
            reasons.append(f"ATR {atr_pct:.1f}% of price - moderate volatility")

    if rsi >= 70 or rsi <= 30:
        score += 15
        reasons.append(f"RSI {rsi:.0f} - momentum extreme, high intraday energy")
    elif rsi >= 60:
        score += 8
        reasons.append(f"RSI {rsi:.0f} - momentum building")

    if macd_hist > macd_hist_prev and macd_hist_prev is not None:
        score += 10
        reasons.append("MACD histogram accelerating")

    if high20 and close >= high20 * 0.98:
        score += 10
        reasons.append("testing 20-day high")
    elif low20 and close <= low20 * 1.02:
        score += 10
        reasons.append("testing 20-day low")

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

    coverage_normalized = (score / max_possible) * 100
    blended = (score * 0.6) + (coverage_normalized * 0.4)
    return round(min(blended, 100.0), 1), reasons


def trade_levels(snap: dict, atr_multiplier: float = 2.5, reward_risk: float = 1.5) -> dict:
    """
    Computes rule-based entry, stop-loss, and target levels using ATR
    (Average True Range) for volatility-adjusted risk sizing. Entry is the
    current close - since the swing scoring logic now selects pullback-to-
    EMA20 setups, we're already buying at/near support, not chasing a high.
    Not a prediction of where price will go - just a defined risk/reward structure.
    """
    close = snap.get("close")
    atr = snap.get("atr14")

    close_is_nan = close is not None and close != close
    atr_is_nan = atr is not None and atr != atr
    if not close or not atr or atr <= 0 or close_is_nan or atr_is_nan:
        return {"entry": None, "stop_loss": None, "target": None, "risk_per_share": None,
                "reward_risk_ratio": None, "note": "insufficient data for trade levels"}

    entry = close

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
                     fund_reasons: list, intraday_tech_score: float = None,
                     intraday_tech_reasons: list = None) -> dict:
    """Produces both swing and intraday composite scores with reasoning.
    If intraday_tech_score isn't provided, falls back to the swing technical
    score (kept for backward compatibility with the backtest, which only
    needs the swing logic)."""
    if intraday_tech_score is None:
        intraday_tech_score = tech_score
        intraday_tech_reasons = tech_reasons

    swing = round(0.55 * tech_score + 0.45 * fund_score, 1)
    intraday = round(0.85 * intraday_tech_score + 0.15 * fund_score, 1)

    return {
        "swing_score": swing,
        "intraday_score": intraday,
        "technical_score": round(tech_score, 1),
        "fundamental_score": round(fund_score, 1),
        "reasons": {
            "technical": tech_reasons,
            "intraday_technical": intraday_tech_reasons,
            "fundamental": fund_reasons,
        },
    }
