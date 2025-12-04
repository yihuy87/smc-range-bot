# range/range_settings.py
# Settings untuk Bot 3 — Range Manipulation Engine

from dataclasses import dataclass


@dataclass
class RangeSettings:
    # Validitas entry (menit)
    valid_minutes: int = 30       # sama seperti bot 1

    # Minimal RR TP2
    min_rr_tp2: float = 1.8

    # Apakah HTF Context wajib align
    use_htf_filter: bool = True

    # SL% sehat (untuk skor)
    min_sl_pct: float = 0.15      # bawah
    max_sl_pct: float = 1.20      # atas

    # Range window (candle 5m)
    range_window: int = 40        # default

    # Mid-zone entry tolerance
    mid_zone_min: float = 0.45
    mid_zone_max: float = 0.55


settings = RangeSettings()
