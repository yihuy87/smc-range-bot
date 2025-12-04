# core/range_settings.py
from dataclasses import dataclass

from config import (
    RANGE_MAX_ENTRY_AGE_CANDLES,
    RANGE_MIN_RR_TP2,
    RANGE_MIN_RANGE_PCT,
    RANGE_SWEEP_PENETRATION_MIN,
    MIN_TIER_TO_SEND,
)


@dataclass
class RangeSettings:
    entry_tf: str = "5m"
    max_entry_age_candles: int = RANGE_MAX_ENTRY_AGE_CANDLES  # misal 6 → 30 menit
    min_rr_tp2: float = RANGE_MIN_RR_TP2                      # misal 1.8
    min_range_pct: float = RANGE_MIN_RANGE_PCT                # minimal range 1H (misal 0.3%)
    sweep_penetration_min: float = RANGE_SWEEP_PENETRATION_MIN  # minimal penetrasi sweep (misal 0.05%)
    min_tier_to_send: str = MIN_TIER_TO_SEND                  # A / A+ / B


range_settings = RangeSettings()
