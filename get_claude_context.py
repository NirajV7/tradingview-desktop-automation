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

def parse_fyers_log(file_path, active_bases, num_lines=200):
    header = get_csv_header(file_path)
    tail = tail_file(file_path, num_lines=num_lines)
    history = {}
    if header and tail:
        reader = csv.reader(tail)
        cols = header.split(",")
        for row in reader:
            if not row or len(row) < len(cols):
                continue
            row_dict = dict(zip(cols, row))
            sym = row_dict.get("symbol")
            base = normalize_symbol(sym)
            if base in active_bases:
                if base not in history:
                    history[base] = []
                history[base].append(row_dict)
    return history

def parse_tv_log(file_path, active_bases, num_lines=200):
    header = get_csv_header(file_path)
    tail = tail_file(file_path, num_lines=num_lines)
    history = {}
    if header and tail:
        reader = csv.reader(tail)
        cols = header.split(",")
        for row in reader:
            if not row or len(row) < len(cols):
                continue
            row_dict = dict(zip(cols, row))
            sym = row_dict.get("symbol")
            base = normalize_symbol(sym)
            if base in active_bases:
                if base not in history:
                    history[base] = []
                history[base].append(row_dict)
    return history

def generate_telemetry():
    # 1. Load active symbols
    watchlist = load_watchlist()
    if not watchlist:
        print("### [ HYBRID BRIDGE WARNING ] ###")
        print("Your watchlist is currently empty. Add symbols via the dashboard first.")
        return

    active_bases = {normalize_symbol(s) for s in watchlist}
    
    # 2. Parse all high-frequency and multi-timeframe closed logs
    fyers_micro = parse_fyers_log(config.FYERS_LOG, active_bases, num_lines=150)
    tv_micro = parse_tv_log(config.TRADING_LOG, active_bases, num_lines=150)
    
    fyers_5m = parse_fyers_log(config.FYERS_LOG_5M, active_bases, num_lines=100)
    tv_5m = parse_tv_log(config.TRADING_LOG_5M, active_bases, num_lines=100)
    
    fyers_15m = parse_fyers_log(config.FYERS_LOG_15M, active_bases, num_lines=100)
    tv_15m = parse_tv_log(config.TRADING_LOG_15M, active_bases, num_lines=100)

    # 3. Output Beautiful Quantitative Markdown Payload
    print(f"============================================================")
    print(f"📊 LIVE TELEMETRY CONTEXT BRIDGE (Fyers + TradingView)")
    print(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST")
    print(f"============================================================\n")

    # Helpers for rendering tables to keep output strictly DRY and clean
    def print_fyers_table(data_dict, base, limit=10):
        ticks = data_dict.get(base, [])
        if ticks:
            # Show last N ticks chronologically
            for fyers in ticks[-limit:]:
                ltp = fyers.get("last_price", "...")
                buy = fyers.get("buy_qty", "0")
                sell = fyers.get("sell_qty", "0")
                vol = fyers.get("volume", "0")
                ts = fyers.get("timestamp", "...").split(" ")[-1]
                print(f"| **{base}** | ₹{ltp} | {buy} | {sell} | {vol} | {ts} |")
        else:
            print(f"| **{base}** | [ No ticks logged ] | - | - | - | - |")

    def print_tv_table(data_dict, base, limit=10, include_tf=False):
        def find_indicator_value(row, keyword, fallback_key=None):
            # 1. Direct match on key containing the clean keyword (case-insensitive)
            for col_key, val in row.items():
                if keyword.lower() in col_key.lower() and val is not None and val != "":
                    return val
            # 2. Direct exact fallback match
            if fallback_key and fallback_key in row and row[fallback_key] is not None and row[fallback_key] != "":
                return row[fallback_key]
            # 3. Fuzzy match on fallback key
            if fallback_key:
                for col_key, val in row.items():
                    if fallback_key.lower() in col_key.lower() and val is not None and val != "":
                        return val
            return "..."

        logs = data_dict.get(base, [])
        logs = sorted(logs, key=lambda x: x.get("timestamp", ""))
        if logs:
            for row in logs[-limit:]:
                price = row.get("price", "...")
                vwap = find_indicator_value(row, "VWAP", "ind_Volume Weighted Average Price")
                ema20 = find_indicator_value(row, "Exponential(20)", "ind_Moving Average Exponential 3")
                ema50 = find_indicator_value(row, "Exponential(50)", "ind_Moving Average Exponential 2")
                ema200 = find_indicator_value(row, "Exponential(200)", "ind_Moving Average Exponential")
                rsi = find_indicator_value(row, "RSI", "ind_Relative Strength Index")
                ts = row.get("timestamp", "...").split(" ")[-1]
                
                # Check for timeframe field
                tf_prefix = ""
                if include_tf:
                    tf_val = row.get("timeframe", "?")
                    tf_prefix = f"{tf_val}m | "

                trend = "WAITING"
                try:
                    if float(price) > float(vwap):
                        trend = "🟢 BULLISH"
                    elif float(price) < float(vwap):
                        trend = "🔴 BEARISH"
                except:
                    pass
                print(f"| **{base}** | {tf_prefix}{price} | {vwap} | {trend} | {ema20} | {ema50} | {ema200} | {rsi} | {ts} |")
        else:
            tf_prefix = " - |" if include_tf else ""
            print(f"| **{base}** | {tf_prefix}- | - | - | - | - | - | - | - |")

    # ==========================================
    # SECTION 1: MICRO-VELOCITY ORDER FLOW (15s/5s)
    # ==========================================
    print("### 1. MICRO-VELOCITY ORDER FLOW (Last 8 Ticks / 1 Min)")
    print("\n#### [1A. Fyers Level-1 Micro Ticks (5s Frequency)]")
    print("| Ticker | Last Price (LTP) | Spread Buy Qty | Spread Sell Qty | Cumulative Vol | Last Tick time |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for base in sorted(active_bases):
        print_fyers_table(fyers_micro, base, limit=8)
        
    print("\n#### [1B. TradingView Micro Indicator Logs (15s Frequency)]")
    print("| Ticker | TF | Price | VWAP | Trend State | EMA(20) | EMA(50) | EMA(200) | RSI | Time |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    for base in sorted(active_bases):
        print_tv_table(tv_micro, base, limit=8, include_tf=True)
    print("")

    # ==========================================
    # SECTION 2: 5-MINUTE WAVE PROGRESSION (Closed Candles)
    # ==========================================
    print("### 2. 5-MINUTE WAVE PROGRESSION (Last 10 Closed 5M Candles)")
    print("\n#### [2A. TradingView 5-Minute Technical Candles]")
    print("| Ticker | Price | VWAP | Trend State | EMA(20) | EMA(50) | EMA(200) | RSI | Time |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    for base in sorted(active_bases):
        print_tv_table(tv_5m, base, limit=10, include_tf=False)
        
    print("\n#### [2B. Fyers 5-Minute Volume & Spread Progression]")
    print("| Ticker | LTP | Spread Buy Qty | Spread Sell Qty | Cumulative Vol | Time |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for base in sorted(active_bases):
        print_fyers_table(fyers_5m, base, limit=10)
    print("")

    # ==========================================
    # SECTION 3: 15-MINUTE MACRO TIDE PROGRESSION (Closed Candles)
    # ==========================================
    print("### 3. 15-MINUTE MACRO TIDE PROGRESSION (Last 10 Closed 15M Candles)")
    print("\n#### [3A. TradingView 15-Minute Technical Candles]")
    print("| Ticker | Price | VWAP | Trend State | EMA(20) | EMA(50) | EMA(200) | RSI | Time |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    for base in sorted(active_bases):
        print_tv_table(tv_15m, base, limit=10, include_tf=False)
        
    print("\n#### [3B. Fyers 15-Minute Volume & Spread Progression]")
    print("| Ticker | LTP | Spread Buy Qty | Spread Sell Qty | Cumulative Vol | Time |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for base in sorted(active_bases):
        print_fyers_table(fyers_15m, base, limit=10)

    print("\n============================================================")
    print("👉 INSTRUCTIONS FOR CLAUDE:")
    print("1. Map these indicators to your active positions queried via mcp_kite_get_positions().")
    print("2. Normalise symbol 'SBIN' with 'NSE:SBIN-EQ' (Fyers) / 'NSE:SBIN' (Zerodha).")
    print("3. Check for crossovers: If price is above VWAP on both 5m and 15m, trend is highly BULLISH.")
    print("============================================================")

if __name__ == "__main__":
    generate_telemetry()
