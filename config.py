# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# === TELEGRAM ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID", "")
TELEGRAM_ADMIN_USERNAME = os.getenv("TELEGRAM_ADMIN_USERNAME", "")

# === BINANCE FUTURES (USDT PERP) ===
BINANCE_REST_URL = "https://fapi.binance.com"
BINANCE_STREAM_URL = "wss://fstream.binance.com/stream"

# ==== PAIR FILTER ====
# Minimum volume USDT dalam 24 jam untuk pair yang boleh discan
MIN_VOLUME_USDT = float(os.getenv("MIN_VOLUME_USDT", "2000000"))

# Max pair yang discan
MAX_USDT_PAIRS = int(os.getenv("MAX_USDT_PAIRS", "200"))

# Interval refresh pair (jam)
REFRESH_PAIR_INTERVAL_HOURS = int(os.getenv("REFRESH_PAIR_INTERVAL_HOURS", "24"))

# ==== SIGNAL FILTER ====
# Tier minimum sinyal yg dikirim
# A+, A, B
MIN_TIER_TO_SEND = os.getenv("MIN_TIER_TO_SEND", "A+")

# Cooldown antar sinyal per pair (detik)
SIGNAL_COOLDOWN_SECONDS = int(os.getenv("SIGNAL_COOLDOWN_SECONDS", "600"))

# ==== RANGE STRATEGY SETTINGS (BOT 3) ====
# Timeframe entry
RANGE_ENTRY_TF = "5m"

# Rata-rata candle untuk mendeteksi range
RANGE_LOOKBACK = int(os.getenv("RANGE_LOOKBACK", "30"))

# Minimum persentase range (0.3% = 0.003)
RANGE_MIN_PCT = float(os.getenv("RANGE_MIN_PCT", "0.003"))

# Maksimum persentase range (anti noise)
RANGE_MAX_PCT = float(os.getenv("RANGE_MAX_PCT", "0.015"))

# Buffer SL dinamis (contoh 0.15% dari harga)
SL_BUFFER_PCT = float(os.getenv("SL_BUFFER_PCT", "0.0015"))

# RR yang digunakan
RR1 = float(os.getenv("RR1", "1.0"))
RR2 = float(os.getenv("RR2", "2.0"))
RR3 = float(os.getenv("RR3", "3.0"))

# ========== RANGE SETTINGS ==========

# Timeframe entry (default 5m)
RANGE_ENTRY_TF = os.getenv("RANGE_ENTRY_TF", "5m")

# HTF filter ON / OFF
RANGE_USE_HTF_FILTER = os.getenv("RANGE_USE_HTF_FILTER", "true").lower() == "true"

# Max usia setup range (berapa candle 5m)
RANGE_MAX_ENTRY_AGE_CANDLES = int(os.getenv("RANGE_MAX_ENTRY_AGE_CANDLES", "6"))

# Minimal RR ke TP2 untuk lolos sinyal
RANGE_MIN_RR_TP2 = float(os.getenv("RANGE_MIN_RR_TP2", "2.0"))
