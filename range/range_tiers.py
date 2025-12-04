# range/range_tiers.py
# Evaluasi kualitas sinyal Range Manipulation Engine Bot 3

from typing import Dict
from core.bot_state import state


def score_signal(meta: Dict) -> int:
    """
    Skoring kualitas sinyal Bot 3 berdasarkan meta:
    
    meta wajib berisi:
      - has_range: bool
      - sweep_ok: bool
      - displacement_ok: bool
      - sl_ok: bool
      - rr_ok: bool
      - volatility_ok: bool
      - structure_ok: bool
      - sl_pct: float
    """

    score = 0

    # -------------------------
    # Core Criteria
    # -------------------------
    if meta.get("has_range"):
        score += 25

    if meta.get("sweep_ok"):
        score += 25

    if meta.get("displacement_ok"):
        score += 20

    if meta.get("structure_ok"):
        score += 15

    if meta.get("volatility_ok"):
        score += 10

    if meta.get("rr_ok"):
        score += 15

    # -------------------------
    # SL Quality Scoring
    # Bonus untuk SL sehat (0.25–0.85%)
    # -------------------------
    sl_pct = float(meta.get("sl_pct", 99))
    if 0.25 <= sl_pct <= 0.85:
        score += 10
    elif sl_pct < 0.20:
        score -= 5
    elif sl_pct > 1.20:
        score -= 5

    # clamp
    score = max(0, min(score, 150))
    return score


def tier_from_score(score: int) -> str:
    """
    Tier berdasarkan score (konsisten dengan bot 1 & bot 2).
    """
    if score >= 120:
        return "A+"
    elif score >= 100:
        return "A"
    elif score >= 80:
        return "B"
    else:
        return "NONE"


def should_send_tier(tier: str) -> bool:
    """
    Bandingkan kualitas tier dengan state.min_tier.
    """
    t_order = {"NONE": 0, "B": 1, "A": 2, "A+": 3}
    min_tier = state.min_tier or "A"
    return t_order.get(tier, 0) >= t_order.get(min_tier, 2)


def evaluate(meta: Dict) -> Dict:
    """
    Wrapper untuk digunakan oleh range_detector.
    Return dict lengkap:
      { score, tier, should_send }
    """

    score = score_signal(meta)
    tier = tier_from_score(score)
    send = should_send_tier(tier)

    return {
        "score": score,
        "tier": tier,
        "should_send": send,
    }
