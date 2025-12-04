# binance/binance_stream.py
# WebSocket scanner Binance Futures 5m + Range Fakeout analyzer (Bot 3).
#
# Catatan penting:
# - HANYA 1 WebSocket multi-stream (seperti bot 1)
# - TIDAK ada HTTP/REST di dalam loop candle-close
# - Range 1H dihitung dari data 5m yang sudah di-buffer (OHLCBufferManager)

import asyncio
import json
import time
from typing import List

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

MAX_5M_CANDLES = 150       # buffer 5m per symbol
PRELOAD_LIMIT_5M = 60      # preload 60 candle 5m lewat REST (sekali di awal refresh)


def _fetch_klines(symbol: str, interval: str, limit: int) -> List[list]:
    """
    Fetch history candle lewat REST.
    DIPAKAI HANYA saat preload awal / refresh pair, BUKAN di loop 5m.
    """
    url = f"{BINANCE_REST_URL}/fapi/v1/klines"
    params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()


async def run_range_bot():
    """
    Main loop Bot 3:
    - Load state (subscribers, VIP, config)
    - Ambil daftar pair USDT perpetual (filter volume)
    - Preload 5m history (sekali di awal / refresh)
    - Connect ke WebSocket multi-stream kline_5m
    - Setiap candle 5m close:
        -> update buffer
        -> cek cooldown
        -> panggil analyze_symbol_range()
        -> kirim sinyal jika valid
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

    # Buffer OHLC 5m (satu untuk semua symbol)
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

                # PRELOAD 5m history sekali di awal / tiap refresh
                print(
                    f"Mulai preload history 5m untuk {len(symbols)} symbol "
                    f"(limit={PRELOAD_LIMIT_5M})..."
                )
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

            # Build multi-stream URL (1 WebSocket untuk semua pair)
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
                        print(
                            "Interval refresh pair tercapai → refresh daftar pair "
                            "dan reconnect WebSocket..."
                        )
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

                    # update buffer dari kline
                    ohlc_mgr.update_from_kline(symbol, kline)
                    candle_closed = bool(kline.get("x", False))

                    # log hanya kalau debug ON dan candle close
                    if state.debug and candle_closed:
                        buf_len = len(ohlc_mgr.get_candles(symbol))
                        print(
                            f"[{time.strftime('%H:%M:%S')}] 5m close: {symbol} "
                            f"— total candle: {buf_len}"
                        )

                    # analisa hanya di candle yang sudah close
                    if not candle_closed:
                        continue

                    # kalau scan belum diaktifkan via /startscan → skip
                    if not state.scanning:
                        continue

                    candles = ohlc_mgr.get_candles(symbol)
                    # butuh minimal beberapa candle untuk bentuk range 1h
                    if len(candles) < 40:
                        continue

                    # cek cooldown per symbol
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

                    # ANALISA RANGE FAKEOUT (NO REST di sini)
                    result = analyze_symbol_range(symbol, candles)
                    if not result:
                        continue

                    text = result["message"]
                    broadcast_signal(text)

                    state.last_signal_time[symbol] = now_ts
                    print(
                        f"[{symbol}] Range Fakeout sinyal dikirim: "
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
