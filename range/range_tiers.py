# range/range_tiers.py
# Skoring & tiering untuk Bot 3 — Range Manipulation Engine.

from typing import Dict
from range.range_settings import settings


def score_signal(meta: Dict) -> int:
    """
    META berisi:
    - range_ok: bool     (range jelas & valid)
    - sweep_ok: bool     (ada manipulasi arah / liquidity grab)
    - displacement_ok: bool
    - entry_zone_ok: bool (mid-range entry)
    - rr_ok: bool
    - htf_ok: bool
    - sl_pct: float
    """

    score = 0

    # Range valid (syarat utama bot 3)
    if meta.get("range_ok"):
        score += 30

    # Sweep / liquidity grab
    if meta.get("sweep_ok"):
        score += 25

    # Displacement keluar dari range → sangat penting
    if meta.get("displacement_ok"):
        score += 20

    # Entry tepat di MID zone (anti manipulasi)
    if meta.get("entry_zone_ok"):
        score += 15

    # RR sehat
    if meta.get("rr_ok"):
        score += 20

    # SL% sehat (mirip bot 1)
    sl_pct = float(meta.get("sl_pct", 0.0))
    if settings.min_sl_pct <= sl_pct <= settings.max_sl_pct:
        score += 10

    # HTF alignment
    if meta.get("htf_ok"):
        score += 15

    # Max cap
    return min(score, 150)


def tier_from_score(score: int) -> str:
    """
    Tier Bot 3:
    - A+ : >= 120
    - A  : 100–119
    - B  : 80–99
    - NONE: < 80
    """
    if score >= 120:
        return "A+"
    elif score >= 100:
        return "A"
    elif score >= 80:
        return "B"
    else:
        return "NONE"


def evaluate_signal_quality(meta: Dict) -> Dict:
    """
    Wrapper standar.
    """
    score = score_signal(meta)
    tier = tier_from_score(score)

    # Default minimal tier A (seperti bot 1)
    should_send = tier in ("A", "A+")

    return {
        "score": score,
        "tier": tier,
        "should_send": should_send,
    }
