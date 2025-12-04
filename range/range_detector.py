# range/range_detector.py
# Engine Bot 3 — Range Manipulation Detection

from typing import Dict, List, Optional
from binance.ohlc_buffer import Candle

from range.htf_context import get_htf_context
from range.range_settings import settings   # file setting bot 3
from range.range_tiers import evaluate_signal_quality


def detect_range_zone(candles: List[Candle]) -> Optional[Dict]:
    """
    Deteksi simple 5m-range:
    - Cari range 20–50 candle terakhir
    - Harga kembali ke mid-range → kandidat setup
    """
    if len(candles) < 60:
        return None

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows  = [c["low"] for c in candles]

    window = 40
    segment_high = max(highs[-window:])
    segment_low  = min(lows[-window:])
    price = closes[-1]

    if segment_high <= segment_low:
        return None

    pos = (price - segment_low) / (segment_high - segment_low)

    # kandidat setup jika berada dekat MID-range
    if 0.45 <= pos <= 0.55:
        return {
            "range_high": segment_high,
            "range_low": segment_low,
            "price": price,
            "position": pos
        }

    return None


def build_levels(range_high: float, range_low: float, price: float) -> Dict[str, float]:
    """
    Entry di MID-range, SL di luar range, TP berdasarkan RR.
    """
    mid = (range_high + range_low) / 2

    if price >= mid:
        side = "short"
        entry = price
        sl = range_high + (range_high * 0.002)
    else:
        side = "long"
        entry = price
        sl = range_low - (range_low * 0.002)

    risk = abs(entry - sl)
    if risk <= 0:
        risk = abs(entry) * 0.003

    rr1, rr2, rr3 = 1.2, 2.0, 3.0

    if side == "long":
        tp1 = entry + rr1 * risk
        tp2 = entry + rr2 * risk
        tp3 = entry + rr3 * risk
    else:
        tp1 = entry - rr1 * risk
        tp2 = entry - rr2 * risk
        tp3 = entry - rr3 * risk

    sl_pct = abs(risk / entry * 100)

    return {
        "side": side,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "sl_pct": sl_pct,
    }


def analyze_symbol_range(symbol: str, candles_5m: List[Candle]) -> Optional[Dict]:
    """
    Analisa lengkap bot 3 — Range Manipulation.
    HTF dipanggil HANYA jika ada kandidat setup.
    """
    # 1. Cari kandidat pola range
    range_hit = detect_range_zone(candles_5m)
    if not range_hit:
        return None

    # 2. Build level entry/SL/TP
    levels = build_levels(
        range_hit["range_high"],
        range_hit["range_low"],
        range_hit["price"]
    )

    # 3. Ambil konteks HTF (dipanggil hanya di sini → NO DELAY)
    htf = get_htf_context(symbol)
    side = levels["side"]

    if side == "long":
        if not htf["htf_ok_long"]:
            return None
    else:
        if not htf["htf_ok_short"]:
            return None

    # 4. Meta untuk skoring
    meta = {
        "range_ok": True,
        "mid_zone_ok": htf["mid_band_ok"],
        "ranging_market": htf["is_ranging_1h"],
        "sl_pct": levels["sl_pct"],
    }

    q = evaluate_signal_quality(meta)
    if not q["should_send"]:
        return None

    tier = q["tier"]
    score = q["score"]

    # 5. Format pesan sinyal
    direction = "LONG" if side == "long" else "SHORT"
    emoji = "🟢" if side == "long" else "🔴"

    message = (
        f"{emoji} RANGE SIGNAL — {symbol.upper()} ({direction})\n"
        f"Entry : `{levels['entry']:.6f}`\n"
        f"SL    : `{levels['sl']:.6f}`\n"
        f"TP1   : `{levels['tp1']:.6f}`\n"
        f"TP2   : `{levels['tp2']:.6f}`\n"
        f"TP3   : `{levels['tp3']:.6f}`\n"
        f"Model : Range Manipulation\n"
        f"Validitas Entry : ±{settings.valid_minutes} menit\n"
        f"Tier : {tier} (Score {score})"
    )

    return {
        "symbol": symbol,
        "side": side,
        "message": message,
        "tier": tier,
        "score": score,
        "levels": levels,
        "htf": htf,
    }
