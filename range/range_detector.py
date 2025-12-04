# range/range_detector.py
# Engine Bot 3 — Range Manipulation Detection

from typing import List, Dict, Optional, Tuple
from binance.ohlc_buffer import Candle
from core.range_settings import settings
from range.range_tiers import evaluate_signal_quality
from range.htf_context import get_htf_context


# ============================================================
# Utility sederhana
# ============================================================

def _body(c: Candle) -> float:
    return abs(c["close"] - c["open"])


def _wick_high(c: Candle) -> float:
    return c["high"]


def _wick_low(c: Candle) -> float:
    return c["low"]


# ============================================================
# 1. DETEKSI RANGE (20–60 candle)
# ============================================================

def detect_range(candles: List[Candle]) -> Optional[Tuple[float, float]]:
    """
    Deteksi range sederhana:
    - cari highest & lowest dari 20–60 candle terakhir
    - range harus kompak (tidak terlalu lebar)
    """

    if len(candles) < settings.range_lookback:
        return None

    sub = candles[-settings.range_lookback:]
    highs = [c["high"] for c in sub]
    lows = [c["low"] for c in sub]

    range_high = max(highs)
    range_low = min(lows)

    width_pct = abs((range_high - range_low) / range_low) * 100

    if width_pct > settings.max_range_width_pct:
        return None

    return range_low, range_high


# ============================================================
# 2. DETEKSI LIQUIDITY SWEEP
# ============================================================

def detect_sweep(candles: List[Candle], range_low: float, range_high: float) -> Optional[str]:
    """
    Return:
        "long"  → sweep bawah lalu kembali masuk range
        "short" → sweep atas lalu kembali masuk range
    """

    last = candles[-1]

    # sweep bawah? (ambil liquidity low)
    if last["low"] < range_low and last["close"] > range_low:
        return "long"

    # sweep atas?
    if last["high"] > range_high and last["close"] < range_high:
        return "short"

    return None


# ============================================================
# 3. DETEKSI DISPLACEMENT (tanda arah jelas setelah sweep)
# ============================================================

def detect_displacement(candles: List[Candle], side: str) -> bool:
    """
    Displacement = candle besar yang bergerak meninggalkan range.
    """

    last = candles[-1]
    body = _body(last)

    avg_body = sum(_body(c) for c in candles[-25:]) / 25

    if side == "long":
        return last["close"] > last["open"] and body > avg_body * settings.displacement_factor

    else:
        return last["close"] < last["open"] and body > avg_body * settings.displacement_factor


# ============================================================
# 4. ENTRY MID-ZONE (anti manipulasi)
# ============================================================

def build_entry_sl_tp(side: str, range_low: float, range_high: float, price: float) -> Dict[str, float]:
    mid = (range_low + range_high) / 2

    if side == "long":
        entry = min(mid, price)
        sl = range_low - abs(mid - range_low) * settings.sl_buffer_multiplier
    else:
        entry = max(mid, price)
        sl = range_high + abs(range_high - mid) * settings.sl_buffer_multiplier

    risk = abs(entry - sl)
    if risk <= 0:
        risk = abs(entry) * 0.002

    # TP berdasarkan RR
    tp1 = entry + risk * settings.rr1 if side == "long" else entry - risk * settings.rr1
    tp2 = entry + risk * settings.rr2 if side == "long" else entry - risk * settings.rr2
    tp3 = entry + risk * settings.rr3 if side == "long" else entry - risk * settings.rr3

    sl_pct = abs(risk / entry) * 100
    lev_min, lev_max = settings.leverage_from_sl(sl_pct)

    return {
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "sl_pct": sl_pct,
        "lev_min": lev_min,
        "lev_max": lev_max,
    }


# ============================================================
# 5. ENGINE — ANALISIS LENGKAP
# ============================================================

def analyze_range_signal(symbol: str, candles: List[Candle]) -> Optional[Dict]:

    if len(candles) < settings.min_candles:
        return None

    # 1) RANGE
    detected = detect_range(candles)
    if not detected:
        return None
    range_low, range_high = detected

    # 2) SWEEP
    direction = detect_sweep(candles, range_low, range_high)
    if not direction:
        return None

    # 3) DISPLACEMENT
    displacement_ok = detect_displacement(candles, direction)
    if not displacement_ok:
        return None

    # 4) ENTRY/SL/TP
    last_price = candles[-1]["close"]
    levels = build_entry_sl_tp(direction, range_low, range_high, last_price)

    # 5) RR check
    risk = abs(levels["entry"] - levels["sl"])
    rr_tp2 = abs(levels["tp2"] - levels["entry"]) / risk
    rr_ok = rr_tp2 >= settings.min_rr_tp2

    # 6) HTF FILTER
    htf = get_htf_context(symbol)
    htf_ok = htf["htf_ok_long"] if direction == "long" else htf["htf_ok_short"]

    # 7) META untuk tiering
    meta = {
        "range_ok": True,
        "sweep_ok": True,
        "displacement_ok": displacement_ok,
        "entry_zone_ok": True,  # mid zone
        "rr_ok": rr_ok,
        "htf_ok": htf_ok,
        "sl_pct": levels["sl_pct"],
    }

    q = evaluate_signal_quality(meta)
    if not q["should_send"]:
        return None

    # Format sinyal
    side_label = "LONG" if direction == "long" else "SHORT"
    emoji = "🟢" if direction == "long" else "🔴"

    lev_text = f"{levels['lev_min']:.0f}x–{levels['lev_max']:.0f}x"
    sl_pct_text = f"{levels['sl_pct']:.2f}%"

    text = (
        f"{emoji} RANGE SIGNAL — {symbol.upper()} ({side_label})\n"
        f"Entry : `{levels['entry']:.6f}`\n"
        f"SL    : `{levels['sl']:.6f}`\n"
        f"TP1   : `{levels['tp1']:.6f}`\n"
        f"TP2   : `{levels['tp2']:.6f}`\n"
        f"TP3   : `{levels['tp3']:.6f}`\n\n"
        f"Model : Range → Sweep → Displacement → Mid Entry\n"
        f"Rekomendasi Leverage : {lev_text} (SL {sl_pct_text})\n"
        f"Tier : {q['tier']} (Score {q['score']})"
    )

    return {
        "symbol": symbol.upper(),
        "side": direction,
        "message": text,
        **levels,
        "tier": q["tier"],
        "score": q["score"],
        "htf": htf,
    }
