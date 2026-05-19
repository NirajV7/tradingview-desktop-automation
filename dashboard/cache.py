import os
import json
import csv
import asyncio
from datetime import datetime, timedelta
from threading import Lock
from fyers_apiv3 import fyersModel
import config
from dashboard.utils import load_watchlist
from indicator_engine import compute_indicators, calculate_adr_percentage, calculate_adr_absolute

class FyersHistoryCache:
    def __init__(self):
        self.lock = Lock()
        self.data_5m = {}  # symbol -> list of indicator dicts
        self.data_15m = {} # symbol -> list of indicator dicts
        self.last_update = None

    def update(self, data_5m, data_15m):
        with self.lock:
            self.data_5m = data_5m
            self.data_15m = data_15m
            self.last_update = datetime.now()

    def get_indicators(self, symbol):
        with self.lock:
            return self.data_5m.get(symbol, []), self.data_15m.get(symbol, [])

fyers_cache = FyersHistoryCache()
RADAR_ALERTS = []  # Ring buffer of alerts: max length 20

def log_fyers_indicators_to_csv(file_path, symbol, candle):
    try:
        file_exists = os.path.exists(file_path)
        if file_exists:
            try:
                with open(file_path, "r") as f:
                    f.seek(0, 2)
                    size = f.tell()
                    # Read the last 8KB of the file to scan for duplicates across all active watchlist symbols
                    f.seek(max(0, size - 8192))
                    tail = f.read()
                    if f"{candle['timestamp']},{symbol}" in tail:
                        return False  # Already logged this timestamp for this stock
            except Exception as e:
                pass
                
        with open(file_path, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["timestamp", "symbol", "price", "ema20", "ema50", "ema200", "rsi", "vwap", "volume", "adr", "adr_abs"])
            
            p = candle.get("close", 0.0)
            e20 = candle.get("ema20")
            e50 = candle.get("ema50")
            e200 = candle.get("ema200")
            rsi = candle.get("rsi")
            v = candle.get("vwap")
            vol = candle.get("volume", 0)
            adr = candle.get("adr")
            adr_abs = candle.get("adr_abs")
            
            e20_val = f"{e20:.2f}" if e20 is not None else ""
            e50_val = f"{e50:.2f}" if e50 is not None else ""
            e200_val = f"{e200:.2f}" if e200 is not None else ""
            rsi_val = f"{rsi:.2f}" if rsi is not None else ""
            v_val = f"{v:.2f}" if v is not None else ""
            adr_val = f"{adr:.2f}" if adr is not None else ""
            adr_abs_val = f"{adr_abs:.2f}" if adr_abs is not None else ""
            
            writer.writerow([
                candle["timestamp"],
                symbol,
                f"{p:.2f}",
                e20_val,
                e50_val,
                e200_val,
                rsi_val,
                v_val,
                vol,
                adr_val,
                adr_abs_val
            ])
        return True
    except Exception as e:
        print(f"[CSV LOG ERROR] Failed to append indicators for {symbol} to {file_path}: {e}")
        return False

def get_last_closed_candle(indicators, timeframe_minutes):
    if not indicators:
        return None
    
    last_candle = indicators[-1]
    try:
        dt = datetime.strptime(last_candle["timestamp"], "%Y-%m-%d %H:%M:%S")
        # Add 5-second grace window to protect against minor clock variances
        end_dt = dt + timedelta(minutes=timeframe_minutes) - timedelta(seconds=5)
        if datetime.now() >= end_dt:
            return last_candle
    except Exception as e:
        pass
        
    if len(indicators) > 1:
        return indicators[-2]
    return last_candle

async def fyers_cache_updater():
    while True:
        try:
            watchlist = load_watchlist()
            active_symbols = watchlist.get("buy", []) + watchlist.get("sell", [])
            if not active_symbols:
                await asyncio.sleep(5)
                continue

            # Load Fyers model
            token_file = config.TOKEN_FILE
            if not os.path.exists(token_file):
                await asyncio.sleep(10)
                continue

            try:
                with open(token_file, "r") as f:
                    token_data = json.load(f)
                    access_token = token_data.get("access_token")
            except Exception as e:
                print(f"[CACHE ERROR] Failed reading token file: {e}")
                await asyncio.sleep(10)
                continue

            if not access_token:
                await asyncio.sleep(10)
                continue

            fyers = fyersModel.FyersModel(
                client_id=config.CLIENT_ID,
                is_async=False,
                token=access_token,
                log_path=os.getcwd()
            )

            new_5m = {}
            new_15m = {}

            today_str = datetime.now().strftime("%Y-%m-%d")
            from_5d_str = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
            from_15d_str = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d")
            from_30d_str = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

            for symbol in active_symbols:
                # Fetch Daily History and compute ADR
                adr_val = None
                adr_abs_val = None
                today_high = None
                today_low = None
                try:
                    res_d = fyers.history({
                        "symbol": symbol,
                        "resolution": "D",
                        "date_format": "1",
                        "range_from": from_30d_str,
                        "range_to": today_str,
                        "cont_flag": "1"
                    })
                    if res_d.get("s") == "ok":
                        d_candles = res_d.get("candles", [])
                        if d_candles:
                            adr_val = calculate_adr_percentage(d_candles, 14)
                            adr_abs_val = calculate_adr_absolute(d_candles, 14)
                            today_high = d_candles[-1][2]
                            today_low = d_candles[-1][3]
                except Exception as e:
                    print(f"[CACHE ERROR] Failed daily ADR for {symbol}: {e}")

                # 5m History
                try:
                    res = fyers.history({
                        "symbol": symbol,
                        "resolution": "5",
                        "date_format": "1",
                        "range_from": from_5d_str,
                        "range_to": today_str,
                        "cont_flag": "1"
                    })
                    if res.get("s") == "ok":
                        candles = res.get("candles", [])
                        if candles:
                            indicators = compute_indicators(candles)
                            for item in indicators:
                                item["adr"] = adr_val
                                item["adr_abs"] = adr_abs_val
                                item["today_high"] = today_high
                                item["today_low"] = today_low
                            new_5m[symbol] = indicators
                            closed_candle = get_last_closed_candle(indicators, 5)
                            if closed_candle:
                                log_fyers_indicators_to_csv(config.FYERS_INDICATORS_5M, symbol, closed_candle)
                except Exception as e:
                    print(f"[CACHE ERROR] Failed 5m for {symbol}: {e}")

                # 15m History
                try:
                    res = fyers.history({
                        "symbol": symbol,
                        "resolution": "15",
                        "date_format": "1",
                        "range_from": from_15d_str,
                        "range_to": today_str,
                        "cont_flag": "1"
                    })
                    if res.get("s") == "ok":
                        candles = res.get("candles", [])
                        if candles:
                            indicators = compute_indicators(candles)
                            for item in indicators:
                                item["adr"] = adr_val
                                item["adr_abs"] = adr_abs_val
                                item["today_high"] = today_high
                                item["today_low"] = today_low
                            new_15m[symbol] = indicators
                            closed_candle = get_last_closed_candle(indicators, 15)
                            if closed_candle:
                                log_fyers_indicators_to_csv(config.FYERS_INDICATORS_15M, symbol, closed_candle)
                except Exception as e:
                    print(f"[CACHE ERROR] Failed 15m for {symbol}: {e}")

                await asyncio.sleep(0.1)

            # Update cache
            fyers_cache.update(new_5m, new_15m)
            print(f"[CACHE SUCCESS] Refreshed indicators for {len(active_symbols)} symbols at {datetime.now().strftime('%H:%M:%S')}")

        except Exception as e:
            print(f"[CACHE ERROR] General exception in updater loop: {e}")

        await asyncio.sleep(60)
