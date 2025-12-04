# range/range_detector.py
# Deteksi setup 1H Range Fake Breakout + 5m Reversal
# (anti breakout palsu, berbasis perilaku likuiditas)

from typing import Dict, List, Optional, Tuple

from binance.ohlc_buffer import Candle
from core.range_settings import range_settings
from range.range_tiers import evaluate_signal_quality


def _compute_1h_range_from_5m(candles_5m: List[Candle]) -> Optional[Tuple[float, float]]:
    """
    Hitung range 1 jam dari 12 candle 5m terakhir SEBELUM candle sweep.
    Kita pakai:
      - 12 candle sebelum sweep (1 jam penuh)
    """
    if len(candles_5m) < 14:
        return None

    # ambil 12 candle sebelum 2 candle terakhir
    # [ -14 ... -3 ] → panjang 12
    window = candles_5m[-14:-2]
    if len(window) < 12:
        return None

    highs = [c["high"] for c in window]
    lows = [c["low"] for c in window]

    range_high = max(highs)
    range_low = min(lows)

    if range_high <= range_low:
        return None

    return range_low, range_high


def _avg_body(candles: List[Candle], lookback: int = 30) -> float:
    sub = candles[-lookback:] if len(candles) > lookback else candles
    if not sub:
        return 0.0
    total = 0.0
    for c in sub:
        total += abs(c["close"] - c["open"])
    return total / len(sub)


def _detect_fakeout(
    candles_5m: List[Candle],
) -> Optional[Dict]:
    """
    Deteksi pola:
      - 12 candle → range 1h (high/low)
      - candle[-2] = sweep fake breakout/breakdown
      - candle[-1] = candle konfirmasi kembali ke range

    Return:
      {
        "side": "long" | "short",
        "range_low": float,
        "range_high": float,
        "sweep_idx": int,
        "confirm_idx": int,
      }
    """
    n = len(candles_5m)
    if n < 14:
        return None

    # range 1h dari 12 candle sebelum sweep
    range_res = _compute_1h_range_from_5m(candles_5m)
    if not range_res:
        return None
    range_low, range_high = range_res

    # cek ukuran range minimal (hindari noise super kecil)
    mid_price = (range_high + range_low) / 2.0
    if mid_price <= 0:
        return None
    range_pct = (range_high - range_low) / mid_price * 100.0
    if range_pct < range_settings.min_range_pct:
        return None

    sweep_idx = n - 2
    confirm_idx = n - 1
    sweep = candles_5m[sweep_idx]
    confirm = candles_5m[confirm_idx]

    sweep_high = sweep["high"]
    sweep_low = sweep["low"]
    sweep_close = sweep["close"]
    confirm_close = confirm["close"]

    # kecilkan noise: butuh penetrasi minimal di luar range
    tol = range_settings.sweep_penetration_min  # misal 0.05% (0.0005)

    # ---------- LONG SETUP (fake breakdown) ----------
    # syarat:
    # - low sweep di bawah range_low dengan penetrasi cukup
    # - sweep_close juga di bawah / dekat range_low
    # - confirm_close kembali di atas range_low dan > sweep_close
    long_candidate = False
    if sweep_low < range_low:
        penetration = (range_low - sweep_low) / range_low * 100.0
        if penetration >= tol:
            if sweep_close <= range_low:
                if (confirm_close > range_low) and (confirm_close > sweep_close):
                    long_candidate = True

    if long_candidate:
        return {
            "side": "long",
            "range_low": range_low,
            "range_high": range_high,
            "sweep_idx": sweep_idx,
            "confirm_idx": confirm_idx,
        }

    # ---------- SHORT SETUP (fake breakout) ----------
    short_candidate = False
    if sweep_high > range_high:
        penetration = (sweep_high - range_high) / range_high * 100.0
        if penetration >= tol:
            if sweep_close >= range_high:
                if (confirm_close < range_high) and (confirm_close < sweep_close):
                    short_candidate = True

    if short_candidate:
        return {
            "side": "short",
            "range_low": range_low,
            "range_high": range_high,
            "sweep_idx": sweep_idx,
            "confirm_idx": confirm_idx,
        }

    return None


def _build_levels(
    side: str,
    range_low: float,
    range_high: float,
    sweep_candle: Candle,
    confirm_candle: Candle,
    rr1: float = 1.2,
    rr2: float = 2.0,
    rr3: float = 3.0,
) -> Dict[str, float]:
    """
    Bangun Entry/SL/TP:
      - Entry di sekitar tepi range (low/high)
      - SL = ekstrem sweep ± buffer dinamis (mirip bot 1)
      - TP = kelipatan R
    """
    last_price = confirm_candle["close"]

    if side == "long":
        raw_entry = range_low
        entry = min(raw_entry, last_price)  # jangan FOMO di atas harga terakhir

        sweep_low = sweep_candle["low"]
        sl_base = min(range_low, sweep_low)
        buffer = max(sl_base * 0.0015, abs(entry) * 0.0005)
        sl = sl_base - buffer

        risk = entry - sl
    else:
        # short
        raw_entry = range_high
        entry = max(raw_entry, last_price)

        sweep_high = sweep_candle["high"]
        sl_base = max(range_high, sweep_high)
        buffer = max(sl_base * 0.0015, abs(entry) * 0.0005)
        sl = sl_base + buffer

        risk = sl - entry

    if risk <= 0:
        risk = abs(entry) * 0.003

    # TP berbasis R:R
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
    Leverage dinamis sama gaya bot 1 & 2.
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
    Analisa utama Bot 3 (1H Range Fakeout):
      - ambil range 1H dari 5m
      - deteksi fake breakout/breakdown + candle konfirmasi
      - bangun Entry/SL/TP dinamis
      - cek RR ke TP2 minimal (from config)
      - skor kualitas → Tier
    """
    if len(candles_5m) < 14:
        return None

    # deteksi fakeout pattern
    patt = _detect_fakeout(candles_5m)
    if not patt:
        return None

    side = patt["side"]
    range_low = patt["range_low"]
    range_high = patt["range_high"]
    sweep_idx = patt["sweep_idx"]
    confirm_idx = patt["confirm_idx"]

    sweep_candle = candles_5m[sweep_idx]
    confirm_candle = candles_5m[confirm_idx]

    levels = _build_levels(side, range_low, range_high, sweep_candle, confirm_candle)

    entry = levels["entry"]
    sl = levels["sl"]
    tp1 = levels["tp1"]
    tp2 = levels["tp2"]
    tp3 = levels["tp3"]
    sl_pct = levels["sl_pct"]

    # validasi RR ke TP2
    risk = abs(entry - sl)
    if risk <= 0:
        return None
    rr_tp2 = abs(tp2 - entry) / risk
    if rr_tp2 < range_settings.min_rr_tp2:
        return None

    # meta untuk scoring
    mid_price = (range_high + range_low) / 2.0
    range_pct = (range_high - range_low) / mid_price * 100.0 if mid_price > 0 else 0.0

    meta = {
        "has_range": True,
        "fakeout_valid": True,
        "range_pct": range_pct,
        "rr_ok": True,
        "sl_pct": sl_pct,
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

    # validitas entry (misal sama seperti bot1: 6 candle = 30 menit)
    max_age_candles = range_settings.max_entry_age_candles
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
        f"{emoji} RANGE FAKEOUT SIGNAL — {symbol.upper()} ({direction_label})\n"
        f"Entry : `{entry:.6f}`\n"
        f"SL    : `{sl:.6f}`\n"
        f"TP1   : `{tp1:.6f}`\n"
        f"TP2   : `{tp2:.6f}`\n"
        f"TP3   : `{tp3:.6f}`\n"
        f"Model : 1H Range Fake Breakout → 5m Reversal\n"
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
        "message": text,
    }
