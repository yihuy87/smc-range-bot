# range/range_tiers.py
# Evaluasi kualitas sinyal RANGE dan tentukan Tier (A+, A, B, NONE).

from typing import Dict

from core.bot_state import state


def score_range_signal(meta: Dict) -> int:
    """
    Skoring berdasarkan kualitas sinyal RANGE.

    meta bisa berisi:
    - has_range: bool        # range jelas (bukan noise)
    - clean_swing: bool      # swing high/low jelas
    - breakout_clear: bool   # candle breakout tegas
    - fvg_ok: bool           # ada inefficiency/FVG sederhana
    - rr_ok: bool            # RR sehat
    - sl_pct: float          # besar SL%
    - htf_alignment: bool    # selaras dengan konteks HTF
    """

    score = 0

    has_range = bool(meta.get("has_range"))
    clean_swing = bool(meta.get("clean_swing"))
    breakout_clear = bool(meta.get("breakout_clear"))
    fvg_ok = bool(meta.get("fvg_ok"))
    rr_ok = bool(meta.get("rr_ok"))
    htf_alignment = bool(meta.get("htf_alignment"))

    sl_pct = float(meta.get("sl_pct", 0.0))

    if has_range:
        score += 25
    if clean_swing:
        score += 20
    if breakout_clear:
        score += 20
    if fvg_ok:
        score += 10
    if rr_ok:
        score += 10

    # SL% sehat (tidak terlalu kecil, tidak terlalu besar)
    if 0.25 <= sl_pct <= 1.20:
        score += 10

    if htf_alignment:
        score += 20

    # batas maksimal
    if score > 150:
        score = 150

    return int(score)


def tier_from_score(score: int) -> str:
    """
    Tier:
    - A+ : >= 120
    - A  : 100–119
    - B  : 80–99
    - NONE : < 80
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
    Urutan: NONE < B < A < A+
    Bandingkan terhadap state.min_tier (diatur via Telegram /mode).
    """
    order = {"NONE": 0, "B": 1, "A": 2, "A+": 3}
    min_tier = state.min_tier or "A"
    return order.get(tier, 0) >= order.get(min_tier, 2)


def evaluate_signal_quality(meta: Dict) -> Dict:
    """
    Wrapper untuk dipanggil dari analyzer RANGE.

    Return:
    {
      "score": int,
      "tier": str,
      "should_send": bool,
    }
    """
    score = score_range_signal(meta)
    tier = tier_from_score(score)
    send = should_send_tier(tier)
    return {
        "score": score,
        "tier": tier,
        "should_send": send,
    }
