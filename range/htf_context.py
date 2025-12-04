# range/htf_context.py
# Konteks HTF (15m & 1h) untuk Range Engine:
# - trend UP / DOWN / RANGE di 1h
# - posisi harga di dalam range (DISCOUNT / PREMIUM / MID) 1h & 15m
# - flag apakah market cenderung RANGING atau TRENDING

from typing import Dict, List, Literal, Optional

import requests

from config import BINANCE_REST_URL


def _fetch_klines(symbol: str, interval: str, limit: int = 150) -> Optional[List[list]]:
    """
    Fetch raw klines futures:
    Return list of Binance kline array, atau None jika gagal.
    """
    url = f"{BINANCE_REST_URL}/fapi/v1/klines"
    params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data
    except Exception as e:
        print(f"[{symbol}] ERROR fetch HTF klines ({interval}):", e)
        return None


def _parse_ohlc(data: List[list]) -> Dict[str, List[float]]:
    highs: List[float] = []
    lows: List[float] = []
    closes: List[float] = []
    for row in data:
        try:
            h = float(row[2])
            l = float(row[3])
            c = float(row[4])
        except (ValueError, TypeError, IndexError):
            continue
        highs.append(h)
        lows.append(l)
        closes.append(c)
    return {"high": highs, "low": lows, "close": closes}


def _detect_trend_1h(hlc: Dict[str, List[float]]) -> Literal["UP", "DOWN", "RANGE"]:
    """
    Deteksi trend kasar 1h pakai perbandingan swing awal–akhir.
    Hanya butuh indikasi: UP / DOWN / RANGE (bukan super presisi).
    """
    highs = hlc["high"]
    lows = hlc["low"]
    n = len(highs)
    if n < 20:
        return "RANGE"

    # ambil beberapa swing kasar: pakai grid sederhana
    step = max(n // 10, 2)
    swing_highs = highs[::step]
    swing_lows = lows[::step]
    if len(swing_highs) < 3 or len(swing_lows) < 3:
        return "RANGE"

    first_h = swing_highs[0]
    last_h = swing_highs[-1]
    first_l = swing_lows[0]
    last_l = swing_lows[-1]

    # threshold kecil supaya tidak noise
    # UP: high & low bergeser naik
    if last_h > first_h * 1.01 and last_l > first_l * 1.005:
        return "UP"
    # DOWN: high & low bergeser turun
    if last_h < first_h * 0.99 and last_l < first_l * 0.995:
        return "DOWN"
    # selain itu anggap RANGE
    return "RANGE"


def _discount_premium(
    hlc: Dict[str, List[float]],
    window: int = 60,
) -> Dict[str, object]:
    """
    Hitung posisi harga terhadap range HIGH/LOW dalam window terakhir.
    Return DISCOUNT / PREMIUM / MID + info range.
    """
    highs = hlc["high"]
    lows = hlc["low"]
    closes = hlc["close"]
    n = len(highs)
    if n < 5:
        return {
            "position": "MID",
            "range_high": None,
            "range_low": None,
            "price": closes[-1] if closes else None,
        }

    start = max(0, n - window)
    seg_high = highs[start:]
    seg_low = lows[start:]
    price = closes[-1]

    range_high = max(seg_high)
    range_low = min(seg_low)
    if range_high <= range_low:
        return {
            "position": "MID",
            "range_high": range_high,
            "range_low": range_low,
            "price": price,
        }

    pos = (price - range_low) / (range_high - range_low)

    if pos <= 0.35:
        position = "DISCOUNT"
    elif pos >= 0.65:
        position = "PREMIUM"
    else:
        position = "MID"

    return {
        "position": position,
        "range_high": range_high,
        "range_low": range_low,
        "price": price,
    }


def get_htf_context(symbol: str) -> Dict[str, object]:
    """
    Ambil konteks 1h & 15m untuk symbol (tanpa indikator klasik).

    Return dict:
    {
      "trend_1h": "UP"|"DOWN"|"RANGE",
      "pos_1h": "DISCOUNT"|"PREMIUM"|"MID",
      "pos_15m": "DISCOUNT"|"PREMIUM"|"MID",
      "is_ranging_1h": bool,
      "mid_band_ok": bool,
      "htf_ok_long": bool,
      "htf_ok_short": bool,
    }

    Catatan:
    - Range Engine lebih suka kondisi "RANGE" dan posisi harga di MID (bukan terlalu ujung).
    - Jika fetch gagal → semua dianggap netral (return context default).
    """
    # default netral
    ctx = {
        "trend_1h": "RANGE",
        "pos_1h": "MID",
        "pos_15m": "MID",
        "is_ranging_1h": True,
        "mid_band_ok": True,
        "htf_ok_long": True,
        "htf_ok_short": True,
    }

    data_1h = _fetch_klines(symbol, "1h", 150)
    data_15m = _fetch_klines(symbol, "15m", 150)

    if not data_1h or not data_15m:
        return ctx  # netral

    hlc_1h = _parse_ohlc(data_1h)
    hlc_15m = _parse_ohlc(data_15m)

    trend_1h = _detect_trend_1h(hlc_1h)
    pos1 = _discount_premium(hlc_1h)
    pos15 = _discount_premium(hlc_15m)

    pos_1h = pos1["position"]
    pos_15m = pos15["position"]

    is_ranging_1h = trend_1h == "RANGE"
    mid_band_ok = (pos_1h == "MID") or (pos_15m == "MID")

    # aturan sederhana:
    # - Untuk Range Engine, setup paling ideal ketika 1h RANGE dan harga dekat MID
    # - Jika trending kuat (UP / DOWN) dan harga di DISCOUNT/PREMIUM ekstrim → tidak ideal untuk range-trade
    htf_ok_long = True
    htf_ok_short = True

    if trend_1h == "UP" and pos_1h == "PREMIUM" and pos_15m == "PREMIUM":
        # terlalu over-extended atas → kurang ideal, terutama long
        htf_ok_long = False
    if trend_1h == "DOWN" and pos_1h == "DISCOUNT" and pos_15m == "DISCOUNT":
        # terlalu over-extended bawah → kurang ideal, terutama short
        htf_ok_short = False

    return {
        "trend_1h": trend_1h,
        "pos_1h": pos_1h,
        "pos_15m": pos_15m,
        "is_ranging_1h": is_ranging_1h,
        "mid_band_ok": mid_band_ok,
        "htf_ok_long": htf_ok_long,
        "htf_ok_short": htf_ok_short,
    }
