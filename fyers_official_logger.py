import os
import csv
import json
import time
import threading
from datetime import datetime
from fyers_apiv3 import fyersModel
from fyers_apiv3.FyersWebsocket import data_ws
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
REDIRECT_URL = os.getenv("FYERS_REDIRECT_URL")
TOKEN_FILE = "fyers_token.json"
WATCHLIST_FILE = "watchlist.json"
LOG_FILE = "fyers_official_log.csv"

# Global state to store the latest data for each symbol
data_store = {}
store_lock = threading.Lock()

def get_symbols():
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r") as f:
            return json.load(f)
    return []

def get_access_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
            return data.get("access_token")
    return None

def log_to_csv():
    """Background thread to write the current data_store to CSV every 2 seconds"""
    print("📊 CSV Logging Thread Started...")
    fieldnames = ['timestamp', 'symbol', 'last_price', 'volume', 'buy_qty', 'sell_qty', 'total_buy_qty', 'total_sell_qty']
    
    while True:
        try:
            with store_lock:
                current_snapshot = list(data_store.values())
            
            if current_snapshot:
                file_needs_header = not os.path.exists(LOG_FILE) or os.stat(LOG_FILE).st_size == 0
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                with open(LOG_FILE, mode='a', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    if file_needs_header:
                        writer.writeheader()
                    for row in current_snapshot:
                        row['timestamp'] = ts
                        writer.writerow(row)
                # print(f"✅ Snapshotted {len(current_snapshot)} symbols to CSV.")
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
    print("🌐 WebSocket Connection Established. Subscribing...")
    symbols = get_symbols()
    
    # Subscribe to BOTH Depth and Full Symbol Data
    # 1. Full Symbol Data (for LTP, Volume)
    fyers_ws.subscribe(symbols=symbols, data_type="SymbolUpdate")
    # 2. Depth Data (for Buy/Sell Quantities)
    fyers_ws.subscribe(symbols=symbols, data_type="DepthUpdate")
    
    print(f"✅ Subscribed to {len(symbols)} symbols for Depth + Price.")
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
        log_path=os.getcwd(),
        litemode=False,
        reconnect=True,
        on_connect=onopen,
        on_close=onclose,
        on_error=onerror,
        on_message=on_message
    )

    # Start the background CSV logger
    threading.Thread(target=log_to_csv, daemon=True).start()

    # Connect to the stream
    fyers_ws.connect()
