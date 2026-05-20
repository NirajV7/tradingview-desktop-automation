import os
import csv
import json
import time
import threading
from datetime import datetime
from fyers_apiv3 import fyersModel
from fyers_apiv3.FyersWebsocket import data_ws
from dotenv import load_dotenv
import config

# Load environment variables
load_dotenv()

CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
REDIRECT_URL = os.getenv("FYERS_REDIRECT_URL")
TOKEN_FILE = config.TOKEN_FILE
WATCHLIST_FILE = config.WATCHLIST_FILE
LOG_FILE = config.FYERS_LOG
FYERS_LOG_5M = config.FYERS_LOG_5M
FYERS_LOG_15M = config.FYERS_LOG_15M

# Global state to store the latest data for each symbol
data_store = {}
store_lock = threading.Lock()

# Dynamic subscription state
subscribed_symbols = set()
subscription_lock = threading.Lock()
fyers_ws = None

def get_symbols():
    symbols = []
    # 1. Base watchlist
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r") as f:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    symbols.extend(loaded)
                elif isinstance(loaded, dict):
                    symbols.extend(loaded.get("buy", []) + loaded.get("sell", []))
        except Exception as e:
            print(f"Error loading watchlist in fyers logger: {e}")
            
    # 2. Radar watchlist
    if os.path.exists(config.RADAR_WATCHLIST_FILE):
        try:
            with open(config.RADAR_WATCHLIST_FILE, "r") as f:
                loaded = json.load(f)
                for item in loaded:
                    sym = item.get("symbol")
                    if sym and sym not in symbols:
                        symbols.append(sym)
        except Exception:
            pass

    # 3. Active trades (format from HDFCLIFE to NSE:HDFCLIFE-EQ)
    if os.path.exists(config.ACTIVE_TRADES_FILE):
        try:
            with open(config.ACTIVE_TRADES_FILE, "r") as f:
                loaded = json.load(f)
                for sym in loaded.keys():
                    full_sym = f"NSE:{sym}-EQ"
                    if full_sym not in symbols:
                        symbols.append(full_sym)
        except Exception:
            pass

    return symbols

def dynamic_subscription_loop():
    """Checks for new symbols in watchlist/radar/active trades and subscribes dynamically."""
    print("🔄 Dynamic Subscription Loop Started...")
    while True:
        try:
            if fyers_ws is None:
                time.sleep(1)
                continue
                
            current_targets = get_symbols()
            new_to_subscribe = []
            
            with subscription_lock:
                for sym in current_targets:
                    if sym not in subscribed_symbols:
                        new_to_subscribe.append(sym)
                        
            if new_to_subscribe:
                print(f"📡 Dynamic subscribing to new symbols: {new_to_subscribe}")
                try:
                    fyers_ws.subscribe(symbols=new_to_subscribe, data_type="SymbolUpdate")
                    fyers_ws.subscribe(symbols=new_to_subscribe, data_type="DepthUpdate")
                    with subscription_lock:
                        subscribed_symbols.update(new_to_subscribe)
                except Exception as ws_err:
                    print(f"⚠️ Dynamic subscription failed: {ws_err}")
        except Exception as e:
            print(f"⚠️ Error in dynamic subscription loop: {e}")
        time.sleep(5)  # Check every 5 seconds

def get_access_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
            return data.get("access_token")
    return None

def get_last_logged_bucket_from_csv(filename, symbol):
    if not os.path.exists(filename) or os.stat(filename).st_size == 0:
        return None
    try:
        with open(filename, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if not rows: return None
            symbol_rows = [r for r in rows if r.get('symbol') == symbol]
            if not symbol_rows: return None
            last_row = symbol_rows[-1]
            ts_str = last_row.get('timestamp')
            if ts_str:
                dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                epoch = int(dt.timestamp())
                return epoch
    except Exception as e:
        print(f"Error reading last bucket from {filename}: {e}")
    return None

def log_to_csv():
    """Background thread to write the current data_store to CSV every 5 seconds"""
    print("📊 CSV Logging Thread Started...")
    fieldnames = ['timestamp', 'symbol', 'last_price', 'volume', 'buy_qty', 'sell_qty', 'total_buy_qty', 'total_sell_qty']
    
    last_logged_5m = {}
    last_logged_15m = {}
    
    while True:
        try:
            with store_lock:
                current_snapshot = [dict(row) for row in data_store.values()] # deep copy rows
            
            if current_snapshot:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # 1. Log to the high-frequency micro CSV
                file_needs_header = not os.path.exists(LOG_FILE) or os.stat(LOG_FILE).st_size == 0
                with open(LOG_FILE, mode='a', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    if file_needs_header:
                        writer.writeheader()
                    for row in current_snapshot:
                        row['timestamp'] = ts
                        writer.writerow(row)
                
                # 2. Log to the 5M and 15M closed candle CSVs upon Epoch Crossover
                now_epoch = int(time.time())
                bucket_5m = now_epoch - (now_epoch % 300)
                bucket_15m = now_epoch - (now_epoch % 900)
                
                for row in current_snapshot:
                    sym = row['symbol']
                    
                    # 5M Closed candle bucket log
                    if sym not in last_logged_5m:
                        last_logged_5m[sym] = get_last_logged_bucket_from_csv(FYERS_LOG_5M, sym)
                    
                    if last_logged_5m[sym] is None or bucket_5m > last_logged_5m[sym]:
                        file_needs_header_5m = not os.path.exists(FYERS_LOG_5M) or os.stat(FYERS_LOG_5M).st_size == 0
                        with open(FYERS_LOG_5M, mode='a', newline='') as f:
                            writer = csv.DictWriter(f, fieldnames=fieldnames)
                            if file_needs_header_5m:
                                writer.writeheader()
                            # Override timestamp to exactly the closed bucket time for beautiful data alignment
                            row_5m = dict(row)
                            row_5m['timestamp'] = ts
                            writer.writerow(row_5m)
                        last_logged_5m[sym] = bucket_5m
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 📊 [FYERS 5M BUCKET CLOSE] Logged for {sym}")
                        
                    # 15M Closed candle bucket log
                    if sym not in last_logged_15m:
                        last_logged_15m[sym] = get_last_logged_bucket_from_csv(FYERS_LOG_15M, sym)
                    
                    if last_logged_15m[sym] is None or bucket_15m > last_logged_15m[sym]:
                        file_needs_header_15m = not os.path.exists(FYERS_LOG_15M) or os.stat(FYERS_LOG_15M).st_size == 0
                        with open(FYERS_LOG_15M, mode='a', newline='') as f:
                            writer = csv.DictWriter(f, fieldnames=fieldnames)
                            if file_needs_header_15m:
                                writer.writeheader()
                            row_15m = dict(row)
                            row_15m['timestamp'] = ts
                            writer.writerow(row_15m)
                        last_logged_15m[sym] = bucket_15m
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 📊 [FYERS 15M BUCKET CLOSE] Logged for {sym}")
                        
        except Exception as e:
            print(f"Logging Error: {e}")
        
        time.sleep(5) # Pulse rate for CSV writing (every 5 seconds)

def on_message(message):
    """Handles incoming WebSocket messages (Both Symbol and Depth updates)"""
    symbol = message.get('symbol')
    if not symbol: return

    with store_lock:
        if symbol not in data_store:
            data_store[symbol] = {
                'symbol': symbol, 'last_price': 0, 'volume': 0, 
                'buy_qty': 0, 'sell_qty': 0, 'total_buy_qty': 0, 'total_sell_qty': 0
            }
        
        # Update Price and Volume from 'sf' (Symbol Full) or '7208' messages
        if 'ltp' in message:
            data_store[symbol]['last_price'] = message['ltp']
        if 'vol_traded_today' in message:
            data_store[symbol]['volume'] = message['vol_traded_today']
        elif 'v' in message:
            data_store[symbol]['volume'] = message['v']

        # Update Depth from 'dp' (Depth) messages
        if 'bid_size1' in message:
            data_store[symbol]['buy_qty'] = message['bid_size1']
        if 'ask_size1' in message:
            data_store[symbol]['sell_qty'] = message['ask_size1']
        
        # Total Buy/Sell if available
        # Note: WebSocket 'dp' usually doesn't have totals, but some modes do.
        # We will use best bid/ask size as the primary liquidity indicators.

def onerror(message):
    print(f"❌ WebSocket Error: {message}")

def onclose(message):
    print(f"🔌 WebSocket Closed: {message}")

def onopen():
    print("🌐 WebSocket Connection Established. Subscribing initial batch...")
    symbols = get_symbols()
    
    # Subscribe to BOTH Depth and Full Symbol Data
    # 1. Full Symbol Data (for LTP, Volume)
    fyers_ws.subscribe(symbols=symbols, data_type="SymbolUpdate")
    # 2. Depth Data (for Buy/Sell Quantities)
    fyers_ws.subscribe(symbols=symbols, data_type="DepthUpdate")
    
    with subscription_lock:
        subscribed_symbols.clear()
        subscribed_symbols.update(symbols)
        
    print(f"✅ Initial subscription complete for {len(symbols)} symbols.")
    fyers_ws.keep_running()

if __name__ == "__main__":
    access_token = get_access_token()
    if not access_token:
        print("❌ No access token found. Please authorize via dashboard.")
        exit()

    # Create the WebSocket instance
    # Fyers expects token in format "appid:accesstoken"
    full_token = f"{CLIENT_ID}:{access_token}"
    
    fyers_ws = data_ws.FyersDataSocket(
        access_token=full_token,
        log_path=os.path.join(config.CWD, "logs"),
        litemode=False,
        reconnect=True,
        on_connect=onopen,
        on_close=onclose,
        on_error=onerror,
        on_message=on_message
    )

    # Start the background CSV logger
    threading.Thread(target=log_to_csv, daemon=True).start()

    # Start the dynamic subscription loop
    threading.Thread(target=dynamic_subscription_loop, daemon=True).start()

    # Connect to the stream
    fyers_ws.connect()
