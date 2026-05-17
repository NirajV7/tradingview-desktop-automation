import os
import json
import csv
from datetime import datetime
import config

def normalize_symbol(sym):
    """Universal symbol normalizer.
    Examples: 'NSE:SBIN-EQ' -> 'SBIN', 'NSE:SBIN' -> 'SBIN', 'SBIN' -> 'SBIN'
    """
    if not sym:
        return ""
    sym_str = str(sym).upper()
    if ":" in sym_str:
        sym_str = sym_str.split(":")[-1]
    if "-" in sym_str:
        sym_str = sym_str.split("-")[0]
    return sym_str.strip()

def get_csv_header(file_path):
    """Reads the first line of the CSV to get column names."""
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, 'r') as f:
            return f.readline().strip()
    except:
        return None

def tail_file(file_path, num_lines=50):
    """Fast, seek-based tail utility. Reads the last 8KB of the file directly."""
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, 'rb') as f:
            f.seek(0, 2)
            file_size = f.tell()
            seek_pos = max(0, file_size - 8192)  # Read trailing 8KB
            f.seek(seek_pos)
            data = f.read().decode('utf-8', errors='ignore')
            lines = data.splitlines()
            if seek_pos > 0 and len(lines) > 1:
                # Throw away first line if it is split/incomplete
                lines = lines[1:]
            return [l.strip() for l in lines[-num_lines:] if l.strip()]
    except:
        try:
            with open(file_path, 'r') as f:
                lines = f.readlines()
                return [l.strip() for l in lines[-num_lines:] if l.strip()]
        except:
            return []

def load_watchlist():
    """Loads active watchlisted symbols."""
    if not os.path.exists(config.WATCHLIST_FILE):
        return []
    try:
        with open(config.WATCHLIST_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def generate_telemetry():
    # 1. Load active symbols
    watchlist = load_watchlist()
    if not watchlist:
        print("### [ HYBRID BRIDGE WARNING ] ###")
        print("Your watchlist is currently empty. Add symbols via the dashboard first.")
        return

    active_bases = {normalize_symbol(s) for s in watchlist}
    
    # 2. Parse Fyers Live Tick Telemetry (Last Ticks)
    fyers_header = get_csv_header(config.FYERS_LOG)
    fyers_tail = tail_file(config.FYERS_LOG, num_lines=100)
    
    latest_fyers_data = {}
    if fyers_header and fyers_tail:
        # Use csv.reader on tail lines to handle commas properly
        reader = csv.reader(fyers_tail)
        cols = fyers_header.split(",")
        for row in reader:
            if not row or len(row) < len(cols):
                continue
            row_dict = dict(zip(cols, row))
            sym = row_dict.get("symbol")
            base = normalize_symbol(sym)
            if base in active_bases:
                latest_fyers_data[base] = row_dict

    # 3. Parse TradingView Technical Indicators (Rolling Window)
    tv_header = get_csv_header(config.TRADING_LOG)
    tv_tail = tail_file(config.TRADING_LOG, num_lines=150)
    
    tv_history = []
    if tv_header and tv_tail:
        reader = csv.reader(tv_tail)
        cols = tv_header.split(",")
        for row in reader:
            if not row or len(row) < len(cols):
                continue
            row_dict = dict(zip(cols, row))
            sym = row_dict.get("symbol")
            base = normalize_symbol(sym)
            if base in active_bases:
                tv_history.append(row_dict)

    # 4. Generate Output Markdown Payload
    print(f"============================================================")
    print(f"📊 LIVE TELEMETRY CONTEXT BRIDGE (Fyers + TradingView)")
    print(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST")
    print(f"============================================================\n")
    
    # SECTION 1: LIVE TICK SNAPSHOTS (Fyers WebSocket)
    print("### 1. LIVE LEVEL-1 ORDER BOOK SNAPSHOTS (Fyers)")
    print("| Ticker | Last Price (LTP) | Spread Buy Qty | Spread Sell Qty | Cumulative Vol | Last Tick time |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- |")
    
    for base in sorted(active_bases):
        fyers = latest_fyers_data.get(base)
        if fyers:
            ltp = fyers.get("last_price", "...")
            buy = fyers.get("buy_qty", "0")
            sell = fyers.get("sell_qty", "0")
            vol = fyers.get("volume", "0")
            ts = fyers.get("timestamp", "...").split(" ")[-1]
            print(f"| **{base}** | ₹{ltp} | {buy} | {sell} | {vol} | {ts} |")
        else:
            print(f"| **{base}** | [ No Fyers tick logged ] | - | - | - | - |")
    print("")

    # SECTION 2: TECHNICAL PROGRESSION (TradingView Scraped Indicators)
    print("### 2. DUAL-TIMEFRAME TECHNICAL LOGS (TradingView)")
    print("| Ticker | TF | Price | VWAP | Trend State | EMA(8) | EMA(21) | RSI | Time |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    
    # For each active ticker, show the last 4 logs (5m and 15m) to let Claude see the recent trend direction
    for base in sorted(active_bases):
        ticker_logs = [row for row in tv_history if normalize_symbol(row.get("symbol")) == base]
        # Sort by timestamp to ensure chronological order
        ticker_logs = sorted(ticker_logs, key=lambda x: x.get("timestamp", ""))
        
        # Keep only the last 4 log rows for this symbol to avoid token bloat
        for row in ticker_logs[-4:]:
            tf = row.get("timeframe", "?")
            price = row.get("price", "...")
            vwap = row.get("ind_Volume Weighted Average Price", row.get("ind_VWAP", "..."))
            
            # Extract EMAs and RSI
            ema8 = row.get("ind_Moving Average Exponential", "...")
            ema21 = row.get("ind_Moving Average Exponential 2", "...")
            rsi = row.get("ind_Relative Strength Index", "...")
            ts = row.get("timestamp", "...").split(" ")[-1]
            
            # Calculate Trend state relative to VWAP
            trend = "WAITING"
            try:
                if float(price) > float(vwap):
                    trend = "🟢 BULLISH"
                elif float(price) < float(vwap):
                    trend = "🔴 BEARISH"
            except:
                pass
                
            print(f"| {base} | {tf}m | {price} | {vwap} | {trend} | {ema8} | {ema21} | {rsi} | {ts} |")
            
    print("\n============================================================")
    print("👉 INSTRUCTIONS FOR CLAUDE:")
    print("1. Map these indicators to your active positions queried via mcp_kite_get_positions().")
    print("2. Normalise symbol 'SBIN' with 'NSE:SBIN-EQ' (Fyers) / 'NSE:SBIN' (Zerodha).")
    print("3. Check for crossovers: If price is above VWAP on both 5m and 15m, trend is highly BULLISH.")
    print("============================================================")

if __name__ == "__main__":
    generate_telemetry()
