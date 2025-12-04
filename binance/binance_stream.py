# binance/binance_stream.py
# WebSocket scanner Binance Futures 5m + Range analyzer.

import asyncio
import json
import time
from typing import Dict, List

import requests
import websockets

from config import BINANCE_STREAM_URL, BINANCE_REST_URL, REFRESH_PAIR_INTERVAL_HOURS
from binance.binance_pairs import get_usdt_pairs
from binance.ohlc_buffer import OHLCBufferManager
from core.bot_state import (
    state,
    load_subscribers,
    load_vip_users,
    cleanup_expired_vip,
    load_bot_state,
)
from range.range_detector import analyze_symbol_range
from telegram.telegram_broadcast import broadcast_signal

# Max candle 5m yang disimpan per symbol
MAX_5M_CANDLES = 120
# Preload awal dari REST (biar history cukup untuk deteksi range)
PRELOAD_LIMIT_5M = 60


def _fetch_klines(symbol: str, interval: str, limit: int) -> List[list]:
    """
    Fetch klines dari REST Binance Futures.
    Dipakai hanya saat preload awal / refresh pair.
    """
    url = f"{BINANCE_REST_URL}/fapi/v1/klines"
    params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()


async def run_range_bot():
    """
    Main loop Range Engine bot:
    - Load subscribers/VIP/state.
    - Ambil daftar pair USDT perpetual berdasarkan volume.
    - Preload 5m history dari REST (sekali di awal / saat refresh pairs).
    - Hubungkan WebSocket multi-stream kline_5m.
    - Build candle 5m per symbol via OHLCBufferManager.
    - Setiap candle close → jalankan Range analyzer → kirim sinyal kalau valid.
    """

    # Load state persistent
    state.subscribers = load_subscribers()
    state.vip_users = load_vip_users()
    state.daily_date = time.strftime("%Y-%m-%d")
    cleanup_expired_vip()
    load_bot_state()

    print(f"Loaded {len(state.subscribers)} subscribers, {len(state.vip_users)} VIP users.")

    symbols: List[str] = []
    last_pairs_refresh: float = 0.0
    refresh_interval = REFRESH_PAIR_INTERVAL_HOURS * 3600

    # Manager buffer candle 5m
    ohlc_mgr = OHLCBufferManager(max_candles=MAX_5M_CANDLES)

    while state.running:
        try:
            now = time.time()
            need_refresh_pairs = (
                not symbols
                or (now - last_pairs_refresh) > refresh_interval
                or state.force_pairs_refresh
            )

            if need_refresh_pairs:
                print("Refresh daftar pair USDT perpetual berdasarkan volume...")
                symbols = get_usdt_pairs(state.max_pairs, state.min_volume_usdt)
                last_pairs_refresh = now
                state.force_pairs_refresh = False

                print(f"Scan {len(symbols)} pair:", ", ".join(s.upper() for s in symbols))

                # Preload history 5m untuk tiap symbol
                print(f"Mulai preload history 5m untuk {len(symbols)} symbol (limit={PRELOAD_LIMIT_5M})...")
                for sym in symbols:
                    try:
                        kl = _fetch_klines(sym.upper(), "5m", PRELOAD_LIMIT_5M)
                        ohlc_mgr.preload_candles(sym.upper(), kl)
                    except Exception as e:
                        print(f"[{sym}] Gagal preload 5m:", e)
                        continue
                print("Preload selesai.")

            if not symbols:
                print("Tidak ada symbol untuk discan. Tidur sebentar...")
                await asyncio.sleep(5)
                continue

            # Build multi-stream URL
            streams = "/".join(f"{s}@kline_5m" for s in symbols)
            ws_url = f"{BINANCE_STREAM_URL}?streams={streams}"

            print(f"Menghubungkan ke WebSocket: {ws_url}")
            async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
                print("WebSocket terhubung.")
                if state.scanning:
                    print("Scan sebelumnya AKTIF → melanjutkan scan otomatis.")
                else:
                    print("Bot dalam mode STANDBY. Gunakan /startscan untuk mulai scan.\n")

                while state.running:
                    # Soft restart diminta dari Telegram
                    if state.request_soft_restart:
                        print("Soft restart diminta → putus WS & refresh engine...")
                        state.request_soft_restart = False
                        break

                    # Perlu refresh daftar pair?
                    if time.time() - last_pairs_refresh > refresh_interval:
                        print("Interval refresh pair tercapai → refresh daftar pair & reconnect WebSocket...")
                        break

                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=60)
                    except asyncio.TimeoutError:
                        if state.debug:
                            print("Timeout menunggu data WebSocket, lanjut...")
                        continue

                    try:
                        data = json.loads(msg)
                    except json.JSONDecodeError:
                        if state.debug:
                            print("Gagal decode JSON dari WebSocket.")
                        continue

                    kline = data.get("data", {}).get("k")
                    if not kline:
                        continue

                    symbol = kline.get("s", "").upper()
                    if not symbol:
                        continue

                    # Update buffer OHLC untuk symbol ini
                    ohlc_mgr.update_from_kline(symbol, kline)
                    candle_closed = bool(kline.get("x", False))

                    # Log optional ketika candle 5m close
                    if state.debug and candle_closed:
                        buf_len = len(ohlc_mgr.get_candles(symbol))
                        print(f"[{time.strftime('%H:%M:%S')}] 5m close: {symbol} — total candle: {buf_len}")

                    # Hanya analisa saat candle 5m sudah close
                    if not candle_closed:
                        continue

                    # Kalau scan belum diaktifkan, skip analisa
                    if not state.scanning:
                        continue

                    candles = ohlc_mgr.get_candles(symbol)
                    if len(candles) < 40:
                        continue

                    # Cooldown per symbol
                    now_ts = time.time()
                    if state.cooldown_seconds > 0:
                        last_ts = state.last_signal_time.get(symbol)
                        if last_ts and now_ts - last_ts < state.cooldown_seconds:
                            if state.debug:
                                print(
                                    f"[{symbol}] Skip cooldown "
                                    f"({int(now_ts - last_ts)}s/{state.cooldown_seconds}s)"
                                )
                            continue

                    # ANALISA RANGE ENGINE
                    result = analyze_symbol_range(symbol, candles)
                    if not result:
                        continue

                    text = result["message"]
                    broadcast_signal(text)

                    state.last_signal_time[symbol] = now_ts
                    print(
                        f"[{symbol}] RANGE sinyal dikirim: "
                        f"Tier {result['tier']} (Score {result['score']}) "
                        f"Entry {result['entry']:.6f} SL {result['sl']:.6f}"
                    )

        except websockets.ConnectionClosed:
            print("WebSocket terputus. Reconnect dalam 5 detik...")
            await asyncio.sleep(5)
        except Exception as e:
            print("Error di run_range_bot (luar):", e)
            print("Coba reconnect dalam 5 detik...")
            await asyncio.sleep(5)

    print("run_range_bot selesai karena state.running = False")
