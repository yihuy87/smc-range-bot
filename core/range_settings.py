# core/range_settings.py
from dataclasses import dataclass

from config import (
    RANGE_ENTRY_TF,
    RANGE_USE_HTF_FILTER,
    RANGE_MAX_ENTRY_AGE_CANDLES,
    RANGE_MIN_RR_TP2,
    MIN_TIER_TO_SEND,
)


@dataclass
class RangeSettings:
    entry_tf: str = RANGE_ENTRY_TF
    use_htf_filter: bool = RANGE_USE_HTF_FILTER
    max_entry_age_candles: int = RANGE_MAX_ENTRY_AGE_CANDLES
    min_rr_tp2: float = RANGE_MIN_RR_TP2
    min_tier_to_send: str = MIN_TIER_TO_SEND

    # tambahan internal (tidak dari .env)
    range_lookback: int = 40          # jumlah candle untuk deteksi range
    min_range_candles: int = 30       # minimal candle yang dianggap range
    max_range_height_pct: float = 0.8 # maksimum tinggi range (dlm %) dibanding harga


range_settings = RangeSettings()
