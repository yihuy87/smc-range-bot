# range/range_detector.py
# Deteksi setup RANGE (sideways + breakout) + bangun Entry/SL/TP.

from typing import Dict, List, Optional, Tuple

import numpy as np

from binance.ohlc_buffer import Candle
from core.range_settings import range_settings
from range.htf_context import get_htf_context
from range.range_tiers import evaluate_signal_quality


def _candles_to_arrays(candles: List[Candle]) -> Dict[str, np.ndarray]:
    """Convert list candle ke NumPy array untuk analisa cepat."""
    o = np.array([c["open"] for c in candles], dtype=float)
    h = np.array([c["high"] for c in candles], dtype=float)
    l = np.array([c["low"] for c in candles], dtype=float)
    c_ = np.array([c["close"] for c in candles], dtype=float)
    v = np.array([c["volume"] for c in candles], dtype=float)
    return {"open": o, "high": h, "low": l, "close": c_, "volume": v}


def _detect_range_zone(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
) -> Optional[Tuple[float, float, float]]:
    """
    Deteksi area range recent:
    - pakai N candle terakhir (tanpa candle breakout)
    - cari high/low & tinggi range
    - pastikan tinggi range relatif kecil (squeeze)
    """
    n = len(closes)
    N = range_settings.range_lookback
    min_n = range_settings.min_range_candles

    if n < min_n + 5:
        return None

    # gunakan N candle sebelum candle terakhir (last candle = kandidat breakout)
    end = n - 1
    start = max(0, end - N)
    h_seg = highs[start:end]
    l_seg = lows[start:end]
    c_seg = closes[start:end]

    if h_seg.size < min_n:
        return None

    range_high = float(np.max(h_seg))
    range_low = float(np.min(l_seg))
    if range_high <= range_low:
        return None

    height = range_high - range_low
    mid = (range_high + range_low) * 0.5
    last_price = float(closes[-1])

    # tinggi range relatif terhadap harga (persen)
    height_pct = abs(height / last_price) * 100.0 if last_price != 0 else 0.0
    if height_pct <= 0:  # aneh
        return None

    # filter: range harus "rapat" (squeeze) tapi tidak super kecil
    if height_pct > range_settings.max_range_height_pct:
        return None

    # tambahan: stdev close di dalam range harus kecil (sideways)
    stdev = float(np.std(c_seg))
    if stdev <= 0:
        return None
    # rasio stdev terhadap tinggi range
    if stdev / height > 0.6:
        # terlalu noisy, bukan range rapi
        return None

    return range_low, range_high, height_pct


def _detect_breakout(
    range_low: float,
    range_high: float,
    last_close: float,
) -> Optional[str]:
    """
    Deteksi apakah last_close breakout dari range.
    Return: "long" / "short" / None
    """
    if last_close <= 0 or range_high <= range_low:
        return None

    # buffer kecil supaya tidak ke-trigger hanya karena wick kecil
    eps = range_high * 0.0005

    if last_close > range_high + eps:
        return "long"
    if last_close < range_low - eps:
        return "short"
    return None


def _build_levels(
    side: str,
    range_low: float,
    range_high: float,
    last_price: float,
    rr1: float = 1.5,
    rr2: float = 2.5,
    rr3: float = 4.0,
) -> Dict[str, float]:
    """
    Bangun Entry/SL/TP:
    - Entry = retest ke batas range (bukan ke harga terakhir)
    - SL = sisi seberang range ± buffer dinamis
    - TP = multiple dari risk (R)
    """
    if side == "long":
        entry = range_high  # buy di retest breakout
        # buffer di bawah range_low
        buffer = max(range_low * 0.0015, abs(entry) * 0.0005)
        sl = range_low - buffer
        risk = entry - sl
    else:
        entry = range_low  # sell di retest breakdown
        buffer = max(range_high * 0.0015, abs(entry) * 0.0005)
        sl = range_high + buffer
        risk = sl - entry

    if risk <= 0:
        # fallback safety
        risk = abs(entry) * 0.003
        if side == "long":
            sl = entry - risk
        else:
            sl = entry + risk

    # TP berdasarkan RR
    if side == "long":
        tp1 = entry + rr1 * risk
        tp2 = entry + rr2 * risk
        tp3 = entry + rr3 * risk
    else:
        tp1 = entry - rr1 * risk
        tp2 = entry - rr2 * risk
        tp3 = entry - rr3 * risk

    sl_pct = abs(risk / entry) * 100.0 if entry != 0 else 0.0
    lev_min, lev_max = recommend_leverage_range(sl_pct)

    return {
        "entry": float(entry),
        "sl": float(sl),
        "tp1": float(tp1),
        "tp2": float(tp2),
        "tp3": float(tp3),
        "sl_pct": float(sl_pct),
        "lev_min": float(lev_min),
        "lev_max": float(lev_max),
    }


def recommend_leverage_range(sl_pct: float) -> Tuple[float, float]:
    """
    Rekomendasi leverage rentang berdasarkan SL%.
    Sama gaya dengan bot-bot sebelumnya.
    """
    if sl_pct <= 0:
        return 5.0, 10.0

    if sl_pct <= 0.25:
        return 25.0, 40.0
    elif sl_pct <= 0.50:
        return 15.0, 25.0
    elif sl_pct <= 0.80:
        return 8.0, 15.0
    elif sl_pct <= 1.20:
        return 5.0, 8.0
    else:
        return 3.0, 5.0


def analyze_symbol_range(symbol: str, candles_5m: List[Candle]) -> Optional[Dict]:
    """
    Analisa RANGE untuk satu symbol pakai data 5m (NumPy):
    - deteksi sideways recent
    - cek breakout candle terakhir
    - bangun Entry/SL/TP
    - cek RR & SL%
    - cek konteks HTF (opsional)
    - skor & tier → hanya kirim jika >= min_tier
    """
    if len(candles_5m) < range_settings.min_range_candles + 5:
        return None

    arr = _candles_to_arrays(candles_5m)
    highs = arr["high"]
    lows = arr["low"]
    closes = arr["close"]

    last_price = float(closes[-1])

    range_info = _detect_range_zone(highs, lows, closes)
    if not range_info:
        return None

    range_low, range_high, height_pct = range_info

    side = _detect_breakout(range_low, range_high, last_price)
    if not side:
        return None

    levels = _build_levels(side, range_low, range_high, last_price)

    entry = levels["entry"]
    sl = levels["sl"]
    tp1 = levels["tp1"]
    tp2 = levels["tp2"]
    tp3 = levels["tp3"]
    sl_pct = levels["sl_pct"]

    risk = abs(entry - sl)
    if risk <= 0:
        return None

    # RR ke TP2 (wajib minimal)
    rr_tp2 = abs(tp2 - entry) / risk
    min_rr = range_settings.min_rr_tp2
    rr_ok = rr_tp2 >= min_rr

    # HTF context
    htf_ctx = get_htf_context(symbol) if range_settings.use_htf_filter else {
        "htf_ok_long": True,
        "htf_ok_short": True,
    }
    if side == "long":
        htf_alignment = bool(htf_ctx.get("htf_ok_long", True))
    else:
        htf_alignment = bool(htf_ctx.get("htf_ok_short", True))

    # meta buat skoring
    meta = {
        "has_range": True,
        "breakout_ok": True,
        "rr_ok": rr_ok,
        "vol_ok": True,
        "sl_pct": sl_pct,
        "htf_alignment": htf_alignment,
    }

    q = evaluate_signal_quality(meta)
    if not q["should_send"]:
        return None

    tier = q["tier"]
    score = q["score"]

    direction_label = "LONG" if side == "long" else "SHORT"
    emoji = "🟢" if side == "long" else "🔴"

    lev_min = levels["lev_min"]
    lev_max = levels["lev_max"]
    lev_text = f"{lev_min:.0f}x–{lev_max:.0f}x"
    sl_pct_text = f"{sl_pct:.2f}%"

    # validitas sinyal
    max_age_candles = range_settings.max_entry_age_candles
    approx_minutes = max_age_candles * 5
    valid_text = f"±{approx_minutes} menit" if approx_minutes > 0 else "singkat"

    # Risk calculator mini
    if sl_pct > 0:
        pos_mult = 100.0 / sl_pct
        example_balance = 100.0
        example_pos = pos_mult * example_balance
        risk_calc = (
            "Risk Calc (contoh risiko 1%):\n"
            f"• SL : {sl_pct_text} → nilai posisi ≈ (1% / SL%) × balance ≈ {pos_mult:.1f}× balance\n"
            f"• Contoh balance 100 USDT → posisi ≈ {example_pos:.0f} USDT\n"
            "(sesuaikan dengan balance & leverage kamu)"
        )
    else:
        risk_calc = "Risk Calc: SL% tidak valid (0), abaikan kalkulasi ini."

    text = (
        f"{emoji} RANGE SIGNAL — {symbol.upper()} ({direction_label})\n"
        f"Entry : `{entry:.6f}`\n"
        f"SL    : `{sl:.6f}`\n"
        f"TP1   : `{tp1:.6f}`\n"
        f"TP2   : `{tp2:.6f}`\n"
        f"TP3   : `{tp3:.6f}`\n"
        "Model : Range Squeeze → Breakout Retest\n"
        f"Rekomendasi Leverage : {lev_text} (SL {sl_pct_text})\n"
        f"Validitas Entry : {valid_text}\n"
        f"Tier : {tier} (Score {score})\n"
        f"{risk_calc}"
    )

    return {
        "symbol": symbol.upper(),
        "side": side,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "sl_pct": sl_pct,
        "lev_min": lev_min,
        "lev_max": lev_max,
        "tier": tier,
        "score": score,
        "range_low": range_low,
        "range_high": range_high,
        "range_height_pct": height_pct,
        "htf_context": htf_ctx,
        "message": text,
    }
