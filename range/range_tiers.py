# range/range_tiers.py
# Evaluasi kualitas sinyal RANGE dan tentukan Tier (A+, A, B, NONE).

from typing import Dict

from core.bot_state import state


def score_signal(meta: Dict) -> int:
    """
    Skoring RANGE:
    - has_range     : ada struktur range yang jelas
    - breakout_ok   : breakout valid
    - rr_ok         : RR ke TP2 sehat
    - vol_ok        : volatilitas / squeeze oke
    - sl_pct        : SL% sehat
    - htf_alignment : searah konteks HTF
    """
    score = 0

    has_range = bool(meta.get("has_range"))
    breakout_ok = bool(meta.get("breakout_ok"))
    rr_ok = bool(meta.get("rr_ok"))
    vol_ok = bool(meta.get("vol_ok"))
    htf_alignment = bool(meta.get("htf_alignment"))
    sl_pct = float(meta.get("sl_pct", 0.0))

    if has_range:
        score += 25
    if breakout_ok:
        score += 25
    if rr_ok:
        score += 15
    if vol_ok:
        score += 10

    # SL sweet spot
    if 0.25 <= sl_pct <= 0.90:
        score += 10

    if htf_alignment:
        score += 20

    return int(min(score, 150))


def tier_from_score(score: int) -> str:
    if score >= 120:
        return "A+"
    elif score >= 100:
        return "A"
    elif score >= 80:
        return "B"
    else:
        return "NONE"


def should_send_tier(tier: str) -> bool:
    order = {"NONE": 0, "B": 1, "A": 2, "A+": 3}
    min_tier = state.min_tier or "A"
    return order.get(tier, 0) >= order.get(min_tier, 2)


def evaluate_signal_quality(meta: Dict) -> Dict:
    score = score_signal(meta)
    tier = tier_from_score(score)
    send = should_send_tier(tier)
    return {"score": score, "tier": tier, "should_send": send}
