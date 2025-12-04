# range/range_settings.py
# Konfigurasi utama Bot 3 — Range Manipulation Engine

from dataclasses import dataclass
from typing import Tuple


@dataclass
class RangeSettings:

    # ============================================================
    # RANGE DETECTION
    # ============================================================
    # berapa candle terakhir untuk membentuk range
    range_lookback: int = 40                 # 20–60 ideal

    # lebar maksimum range (dalam %)
    max_range_width_pct: float = 1.2         # agar range cukup ketat (anti noise)

    # minimal jumlah candle total (agar pattern matang)
    min_candles: int = 50


    # ============================================================
    # DISPLACEMENT
    # ============================================================
    # faktor pembesar body candle untuk menganggap itu displacement
    displacement_factor: float = 1.6         # 1.5–2.0


    # ============================================================
    # STOP LOSS DINAMIS
    # ============================================================
    # SL = low/high range ± buffer * distance(mid, extreme)
    sl_buffer_multiplier: float = 0.35       # 0.3–0.45 aman


    # ============================================================
    # RISK-REWARD (RR)
    # ============================================================
    rr1: float = 1.2
    rr2: float = 1.8
    rr3: float = 3.0

    # syarat minimal RR TP2 (mirip bot 2 config)
    min_rr_tp2: float = 1.5                  # lebih longgar dari bot 2 (1.8)


    # ============================================================
    # LEVERAGE ADAPTIF
    # ============================================================
    def leverage_from_sl(self, sl_pct: float) -> Tuple[float, float]:
        """
        Leverage dinamis berdasarkan SL%.
        Semakin kecil SL → leverage lebih tinggi.
        Sama gaya bot 1 & bot 2.
        """
        if sl_pct <= 0:
            return 5.0, 10.0

        if sl_pct <= 0.25:
            return 20.0, 35.0
        elif sl_pct <= 0.50:
            return 12.0, 20.0
        elif sl_pct <= 0.80:
            return 6.0, 12.0
        elif sl_pct <= 1.20:
            return 4.0, 6.0
        else:
            return 2.0, 4.0


# expose settings global
settings = RangeSettings()
