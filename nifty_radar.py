import os
import csv
import json
import time
import requests
import threading
from datetime import datetime
from collections import deque
from fyers_apiv3.FyersWebsocket import data_ws
from dotenv import load_dotenv
import config

# Load environment variables
load_dotenv()

CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
TOKEN_FILE = config.TOKEN_FILE
NIFTY_FEED_CSV = config.NIFTY_FEED_CSV
NIFTY_SPIKES_LOG = config.NIFTY_SPIKES_LOG
SYMBOLS = config.NIFTY_SYMBOLS

# Threshold Configuration
VOLUME_SPIKE_RATIO = 3.0  # 300% above 20-min average volume
PRICE_MOMENTUM_PCT = 0.25  # Minimum 0.25% absolute price change in 1 minute

# Global state memory
# active_tick_store = {symbol: {"ltp": price, "today_vol": cumulative_volume}}
active_tick_store = {}
tick_lock = threading.Lock()

# rolling_volumes = {symbol: deque([v1, v2, ...], maxlen=20)}
rolling_volumes = {sym: deque(maxlen=20) for sym in SYMBOLS}

# open_minute_data = {symbol: {"open": o, "high": h, "low": l, "close": c, "start_vol": v}}
open_minute_data = {}

def get_access_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
            return data.get("access_token")
    return None

def load_historical_volumes():
    """Reads the existing nifty_50_feed.csv on boot to pre-populate rolling volume averages."""
    if not os.path.exists(NIFTY_FEED_CSV) or os.stat(NIFTY_FEED_CSV).st_size == 0:
        print("📝 No historical Nifty 50 feed found. Radar will build memory dynamically.")
        return

    print("⚡ Pre-loading historical Nifty 50 volume logs for instant readiness...")
    try:
        temp_data = {sym: [] for sym in SYMBOLS}
        with open(NIFTY_FEED_CSV, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                sym = row.get("symbol")
                vol = row.get("volume")
                if sym in temp_data and vol:
                    try:
                        temp_data[sym].append(float(vol))
                    except ValueError:
                        pass
        
        # Load the last 20 records into each rolling volume deque
        loaded_count = 0
        for sym in SYMBOLS:
            history = temp_data[sym][-20:]
            for v in history:
                rolling_volumes[sym].append(v)
            if history:
                loaded_count += 1
                
        print(f"✅ Pre-loaded historical logs for {loaded_count} symbols successfully.")
    except Exception as e:
        print(f"⚠️ Error loading historical logs: {e}")

def enforce_log_rotation():
    """Keeps the CSV feed clean by limiting to the last 5 days of data (~15,000 rows)."""
    if not os.path.exists(NIFTY_FEED_CSV) or os.stat(NIFTY_FEED_CSV).st_size < 10 * 1024 * 1024:
        return  # Skip if less than 10MB
        
    try:
        print("🧹 Rotating Nifty 50 feed CSV to prevent file bloat...")
        rows = []
        with open(NIFTY_FEED_CSV, 'r') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows = list(reader)
            
        # Retain only the last 15,000 rows (~5 trading days of data)
        rotated_rows = rows[-15000:]
        with open(NIFTY_FEED_CSV, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rotated_rows)
        print("✅ Log rotation completed.")
    except Exception as e:
        print(f"⚠️ Failed to rotate Nifty 50 log: {e}")

def trigger_alert(symbol, ltp, volume_ratio, price_change_pct):
    """Sends a real-time spike alert to the local FastAPI server and logs to spikes log."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. Post to FastAPI Local Server
    try:
        payload = {
            "symbol": symbol.replace("NSE:", "").replace("-EQ", ""),
            "ltp": ltp,
            "volume_ratio": round(volume_ratio, 2),
            "price_change": round(price_change_pct, 2)
        }
        res = requests.post("http://127.0.0.1:8080/api/radar/alert", json=payload, timeout=2)
        print(f"📡 Radar Alert Sent to Dashboard: {payload} | Status: {res.status_code}")
    except Exception as e:
        print(f"⚠️ Failed to post alert to dashboard: {e}")

    # 2. Append to Spikes text log
    try:
        log_entry = f"{ts} | {symbol:15} | Price: ₹{ltp:<8} | Volume: {volume_ratio:5.2f}x Avg | Delta: {price_change_pct:+.2f}%\n"
        with open(NIFTY_SPIKES_LOG, 'a') as f:
            f.write(log_entry)
    except Exception as e:
        print(f"⚠️ Failed to write to spikes log: {e}")

def aggregate_and_flush_minute():
    """Runs on a 60-second loop to build candles, detect spikes, and write to CSV."""
    print("⏲️ Batch Aggregation Engine Started...")
    fieldnames = ["timestamp", "symbol", "open", "high", "low", "close", "volume"]
    
    while True:
        # Align perfectly to the close of the current minute
        now = time.time()
        sleep_time = 60.0 - (now % 60.0)
        time.sleep(sleep_time)
        
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:00")
        
        try:
            with tick_lock:
                snapshot = dict(active_tick_store)
                
            batch_rows = []
            
            for sym in SYMBOLS:
                tick = snapshot.get(sym)
                if not tick:
                    continue
                
                ltp = tick["ltp"]
                vol_now = tick["today_vol"]
                
                # Retrieve or initialize the open candle for this minute
                candle = open_minute_data.get(sym)
                
                if candle is None:
                    # First minute block initialization
                    open_minute_data[sym] = {
                        "open": ltp, "high": ltp, "low": ltp, "close": ltp, "start_vol": vol_now
                    }
                    continue
                
                # Fetch consolidated minute boundaries
                o = candle["open"]
                h = candle["high"]
                l = candle["low"]
                c = ltp  # Current LTP is the close of the minute
                vol_delta = max(0, vol_now - candle["start_vol"])
                
                # Format CSV output row
                row = {
                    "timestamp": ts, "symbol": sym, "open": o, "high": h, "low": l, "close": c, "volume": vol_delta
                }
                batch_rows.append(row)
                
                # Calculate Spike Triggers if we have enough rolling average volume
                rolling_queue = rolling_volumes[sym]
                if len(rolling_queue) >= 5 and vol_delta > 0:
                    avg_vol = sum(rolling_queue) / len(rolling_queue)
                    vol_ratio = vol_delta / avg_vol if avg_vol > 0 else 0
                    price_change_pct = ((c - o) / o) * 100 if o > 0 else 0
                    
                    # Detect Spikes
                    if vol_ratio >= VOLUME_SPIKE_RATIO and abs(price_change_pct) >= PRICE_MOMENTUM_PCT:
                        trigger_alert(sym, c, vol_ratio, price_change_pct)
                
                # Update rolling volume queue with this minute's closed volume
                rolling_queue.append(vol_delta)
                
                # Reset open candle boundary for the next minute
                open_minute_data[sym] = {
                    "open": ltp, "high": ltp, "low": ltp, "close": ltp, "start_vol": vol_now
                }
            
            # Flush batch candles to CSV in a single transaction
            if batch_rows:
                file_needs_header = not os.path.exists(NIFTY_FEED_CSV) or os.stat(NIFTY_FEED_CSV).st_size == 0
                with open(NIFTY_FEED_CSV, mode='a', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    if file_needs_header:
                        writer.writeheader()
                    writer.writerows(batch_rows)
                    
            # Enforce log rotation safety limits
            enforce_log_rotation()
            
        except Exception as e:
            print(f"⚠️ Error during batch minute aggregation: {e}")

def on_message(message):
    """Processes real-time ticks from Fyers WebSocket."""
    symbol = message.get('symbol')
    if not symbol or symbol not in SYMBOLS:
        return
        
    ltp = message.get('ltp')
    vol = message.get('vol_traded_today') or message.get('v')
    
    if ltp is None:
        return
        
    with tick_lock:
        # 1. Update active tick store
        if symbol not in active_tick_store:
            active_tick_store[symbol] = {"ltp": ltp, "today_vol": vol or 0}
        else:
            active_tick_store[symbol]["ltp"] = ltp
            if vol is not None:
                active_tick_store[symbol]["today_vol"] = vol
                
        # 2. Update the in-minute candle boundaries
        if symbol not in open_minute_data:
            open_minute_data[symbol] = {
                "open": ltp, "high": ltp, "low": ltp, "close": ltp, "start_vol": vol or 0
            }
        else:
            candle = open_minute_data[symbol]
            candle["high"] = max(candle["high"], ltp)
            candle["low"] = min(candle["low"], ltp)
            candle["close"] = ltp

def onerror(message):
    print(f"❌ Radar WebSocket Error: {message}")

def onclose(message):
    print(f"🔌 Radar WebSocket Closed: {message}")

def onopen():
    print("🌐 Radar WebSocket Connected. Subscribing to Nifty 50...")
    # Subscribe to full symbol update (which includes ltp and volume traded today)
    fyers_ws.subscribe(symbols=SYMBOLS, data_type="SymbolUpdate")
    print(f"📡 Subscribed successfully to {len(SYMBOLS)} Nifty 50 stocks.")
    fyers_ws.keep_running()

if __name__ == "__main__":
    access_token = get_access_token()
    if not access_token:
        print("❌ No Fyers access token found. Please authorize via dashboard.")
        exit()

    # Pre-load historical rolling volumes
    load_historical_volumes()

    # Launch batch aggregation loop in background thread
    threading.Thread(target=aggregate_and_flush_minute, daemon=True).start()

    # Create and connect Fyers WebSocket
    full_token = f"{CLIENT_ID}:{access_token}"
    fyers_ws = data_ws.FyersDataSocket(
        access_token=full_token,
        log_path=os.getcwd(),
        litemode=False,
        reconnect=True,
        on_connect=onopen,
        on_close=onclose,
        on_error=onerror,
        on_message=on_message
    )

    fyers_ws.connect()
