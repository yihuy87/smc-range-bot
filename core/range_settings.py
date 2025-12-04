# core/range_settings.py
# Setting utama engine RANGE BOT (Bot 3)

from dataclasses import dataclass


@dataclass
class RangeSettings:
    # Berapa candle terakhir untuk mendeteksi range
    lookback: int = 120

    # Minimal lebar range secara persentase (%) agar dianggap valid
    min_range_pct: float = 0.35

    # RR minimal terhadap breakout
    min_rr_break: float = 1.8

    # Usia maksimal setup (candle 5m)
    max_age_candles: int = 6  # 6 candle = 30 menit

    # Filter HTF boleh hidup/mati
    use_htf_filter: bool = True


range_settings = RangeSettings()
