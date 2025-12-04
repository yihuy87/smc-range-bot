# range/range_detector.py
# Deteksi setup RANGE-REVERSION + bangun Entry/SL/TP.

from typing import Dict, List, Optional, Tuple

from binance.ohlc_buffer import Candle
from range.htf_context import get_htf_context
from range.range_tiers import evaluate_signal_quality

# range_settings disimpan di core, tapi kita pakai getattr supaya aman
try:
    from core.range_settings import range_settings as _rs  # type: ignore[attr-defined]
except Exception:  # fallback kalau belum ada
    _rs = None


def _get_min_rr_tp2() -> float:
    if _rs is None:
        return 1.8
    return float(getattr(_rs, "min_rr_tp2", 1.8))


def _get_max_entry_age_candles() -> int:
    if _rs is None:
        return 6
    return int(getattr(_rs, "max_entry_age_candles", 6))


def _avg_range_height(candles: List[Candle], lookback: int = 60) -> float:
    sub = candles[-lookback:] if len(candles) > lookback else candles
    if not sub:
        return 0.0
    total = 0.0
    for c in sub:
        total += c["high"] - c["low"]
    return total / len(sub)


def _detect_range_zone(
    candles: List[Candle],
    lookback: int = 60,
) -> Optional[Tuple[float, float, str]]:
    """
    Deteksi range sederhana di lookback terakhir.
    Return (range_low, range_high, side) atau None.
    side:
      - "long"  → harga di zona bawah range (discount) → cari LONG
      - "short" → harga di zona atas range (premium)  → cari SHORT
    """
    if len(candles) < lookback:
        return None

    recent = candles[-lookback:]
    highs = [c["high"] for c in recent]
    lows = [c["low"] for c in recent]
    closes = [c["close"] for c in recent]

    if not highs or not lows or not closes:
        return None

    r_high = max(highs)
    r_low = min(lows)
    last_price = closes[-1]

    width = r_high - r_low
    if width <= 0:
        return None

    mid = (r_high + r_low) * 0.5
    if mid <= 0:
        return None

    range_width_pct = (width / mid) * 100.0

    # Range terlalu sempit → noise, terlalu lebar → bukan range intraday sehat
    if range_width_pct < 0.4 or range_width_pct > 3.0:
        return None

    # Zona bawah & atas (35% dari range)
    bottom_zone = r_low + width * 0.35
    top_zone = r_high - width * 0.35

    if last_price <= bottom_zone:
        side = "long"
    elif last_price >= top_zone:
        side = "short"
    else:
        return None

    return r_low, r_high, side


def recommend_leverage_range(sl_pct: float) -> Tuple[float, float]:
    """
    Rekomendasi leverage rentang berdasarkan SL%.
    Mirip pola bot-bot sebelumnya.
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


def _build_levels(
    side: str,
    range_low: float,
    range_high: float,
    last_price: float,
    rr1: float = 1.2,
    rr2: float = 2.0,
    rr3: float = 3.0,
) -> Dict[str, float]:
    """
    Bangun Entry/SL/TP untuk RANGE-REVERSION:
    - Entry dekat tepi range (bukan di tengah).
    - SL sedikit di luar range (buffer dinamis).
    - TP pakai kelipatan R (RR1/RR2/RR3).
    """
    width = range_high - range_low
    if width <= 0:
        # fallback kecil
        width = abs(last_price) * 0.003

    buffer = max(width * 0.15, abs(last_price) * 0.001)

    if side == "long":
        entry = min(last_price, range_low + width * 0.10)
        sl = range_low - buffer
        risk = entry - sl
    else:
        entry = max(last_price, range_high - width * 0.10)
        sl = range_high + buffer
        risk = sl - entry

    if risk <= 0:
        risk = abs(entry) * 0.003

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


def analyze_symbol_range(symbol: str, candles_5m: List[Candle]) -> Optional[Dict]:
    """
    Analyzer utama RANGE ENGINE untuk satu symbol.
    Dipanggil setiap candle 5m close dari binance_stream.
    """
    if len(candles_5m) < 60:
        return None

    # Deteksi range & sisi (long/short)
    detected = _detect_range_zone(candles_5m, lookback=60)
    if not detected:
        return None

    range_low, range_high, side = detected
    last_price = candles_5m[-1]["close"]

    levels = _build_levels(side, range_low, range_high, last_price)

    entry = levels["entry"]
    sl = levels["sl"]
    tp1 = levels["tp1"]
    tp2 = levels["tp2"]
    tp3 = levels["tp3"]
    sl_pct = levels["sl_pct"]

    # Validasi RR TP2
    risk = abs(entry - sl)
    if risk <= 0:
        return None

    rr_tp2 = abs(tp2 - entry) / risk
    min_rr = _get_min_rr_tp2()
    rr_ok = rr_tp2 >= min_rr

    # HTF context
    htf_ctx = get_htf_context(symbol)
    if side == "long":
        htf_alignment = bool(htf_ctx.get("htf_ok_long", True))
    else:
        htf_alignment = bool(htf_ctx.get("htf_ok_short", True))

    # Meta untuk scorring
    meta = {
        "has_range": True,
        "clean_swing": True,       # versi pertama: asumsi range rapi
        "breakout_clear": True,    # nanti bisa diperketat
        "fvg_ok": True,            # placeholder; kita anggap ada inefficiency minor
        "rr_ok": rr_ok,
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

    # Validitas sinyal (pakai max_entry_age_candles dari settings)
    max_age_candles = _get_max_entry_age_candles()
    approx_minutes = max_age_candles * 5
    valid_text = f"±{approx_minutes} menit" if approx_minutes > 0 else "singkat"

    # Risk calculator mini
    if sl_pct > 0:
        pos_mult = 100.0 / sl_pct
        example_balance = 100.0
        example_pos = pos_mult * example_balance
        risk_calc = (
            f"Risk Calc (contoh risiko 1%):\n"
            f"• SL : {sl_pct_text} → nilai posisi ≈ (1% / SL%) × balance ≈ {pos_mult:.1f}× balance\n"
            f"• Contoh balance 100 USDT → posisi ≈ {example_pos:.0f} USDT\n"
            f"(sesuaikan dengan balance & leverage kamu)"
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
        f"Model : Range Reversion Engine\n"
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
        "htf_context": htf_ctx,
        "message": text,
}
