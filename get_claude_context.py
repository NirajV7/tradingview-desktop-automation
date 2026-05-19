import os
import json
import csv
from datetime import datetime, timedelta
import config
from fyers_apiv3 import fyersModel
from indicator_engine import compute_indicators, calculate_adr_percentage, calculate_adr_absolute
from dashboard_app import get_last_closed_candle

def get_fyers_client():
    if os.path.exists(config.TOKEN_FILE):
        try:
            with open(config.TOKEN_FILE, "r") as f:
                token_data = json.load(f)
                access_token = token_data.get("access_token")
                if access_token:
                    return fyersModel.FyersModel(
                        client_id=config.CLIENT_ID,
                        is_async=False,
                        token=access_token,
                        log_path=os.path.join(config.CWD, "logs")
                    )
        except Exception as e:
            print(f"Error loading Fyers client: {e}")
    return None

def fetch_fyers_indicators(symbol, resolution, days_back):
    fyers = get_fyers_client()
    if not fyers:
        return []
    
    # Calculate dates
    today_str = datetime.now().strftime("%Y-%m-%d")
    from_date_str = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    
    data = {
        "symbol": symbol,
        "resolution": resolution,
        "date_format": "1",
        "range_from": from_date_str,
        "range_to": today_str,
        "cont_flag": "1"
    }
    
    try:
        response = fyers.history(data=data)
        if response.get("s") == "ok":
            candles = response.get("candles", [])
            if candles:
                return compute_indicators(candles)
    except Exception as e:
        print(f"Error fetching Fyers history for {symbol} ({resolution}): {e}")
    return []


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
    tv_micro = {}  # Archived
    
    fyers_5m = parse_fyers_log(config.FYERS_LOG_5M, active_bases, num_lines=100)
    tv_5m = {}  # Archived
    
    fyers_15m = parse_fyers_log(config.FYERS_LOG_15M, active_bases, num_lines=100)
    tv_15m = {}  # Archived

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

        def evaluate_trend_state(price, vwap, ema20, ema50, ema200, rsi):
            try:
                p = float(price)
                v = float(vwap)
                e20 = float(ema20)
                e50 = float(ema50)
                e200 = float(ema200)
                r = float(rsi)
                
                # Bullish conditions
                is_bull_baseline = p > v
                is_bull_structure = e20 > e50
                is_bull_anchor = p > e200
                is_bull_momentum = r > 50
                
                # Bearish conditions
                is_bear_baseline = p < v
                is_bear_structure = e20 < e50
                is_bear_anchor = p < e200
                is_bear_momentum = r < 50
                
                if is_bull_baseline and is_bull_structure and is_bull_anchor and is_bull_momentum:
                    if r > 70:
                        return "⚠️ OVERBOUGHT"
                    return "🟢 BULLISH"
                    
                if is_bear_baseline and is_bear_structure and is_bear_anchor and is_bear_momentum:
                    if r < 30:
                        return "⚠️ OVERSOLD"
                    return "🔴 BEARISH"
                    
                return "🟡 CONGESTION"
            except:
                return "🟡 CONGESTION"

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

                trend = evaluate_trend_state(price, vwap, ema20, ema50, ema200, rsi)
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
    print("")

    # ==========================================
    # SECTION 2: 5-MINUTE WAVE PROGRESSION (Closed Candles)
    # ==========================================
    print("### 2. 5-MINUTE WAVE PROGRESSION (Last 10 Closed 5M Candles)")
    print("\n#### [2A. Fyers 5-Minute Volume & Spread Progression]")
    print("| Ticker | LTP | Spread Buy Qty | Spread Sell Qty | Cumulative Vol | Time |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for base in sorted(active_bases):
        print_fyers_table(fyers_5m, base, limit=10)
    print("")

    # ==========================================
    # SECTION 3: 15-MINUTE MACRO TIDE PROGRESSION (Closed Candles)
    # ==========================================
    print("### 3. 15-MINUTE MACRO TIDE PROGRESSION (Last 10 Closed 15M Candles)")
    print("\n#### [3A. Fyers 15-Minute Volume & Spread Progression]")
    print("| Ticker | LTP | Spread Buy Qty | Spread Sell Qty | Cumulative Vol | Time |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for base in sorted(active_bases):
        print_fyers_table(fyers_15m, base, limit=10)

    # ==========================================
    # SECTION 4: FYERS-BACKED SERVER-SIDE INDICATOR ENGINE
    # ==========================================
    print("### 4. FYERS-BACKED TECHNICAL INDICATOR ENGINE (Real-Time Server Calculations)")
    print("\n#### [4A. Fyers 5-Minute Technical Candles (Calculated from Fyers API)]")
    print("| Ticker | Price | VWAP | Trend State | EMA(20) | EMA(50) | EMA(200) | RSI | ADR (%) | ADR (Abs) | Time |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    
    def evaluate_fyers_trend(p, v, e20, e50, e200, r):
        try:
            # Bullish
            is_bull_baseline = p > v
            is_bull_structure = e20 > e50
            is_bull_anchor = p > e200
            is_bull_momentum = r > 50
            
            # Bearish
            is_bear_baseline = p < v
            is_bear_structure = e20 < e50
            is_bear_anchor = p < e200
            is_bear_momentum = r < 50
            
            if is_bull_baseline and is_bull_structure and is_bull_anchor and is_bull_momentum:
                if r > 70: return "⚠️ OVERBOUGHT"
                return "🟢 BULLISH"
            if is_bear_baseline and is_bear_structure and is_bear_anchor and is_bear_momentum:
                if r < 30: return "⚠️ OVERSOLD"
                return "🔴 BEARISH"
            return "🟡 CONGESTION"
        except:
            return "🟡 CONGESTION"

    for base in sorted(active_bases):
        # Find full symbol from watchlist
        full_symbol = next((s for s in watchlist if normalize_symbol(s) == base), f"NSE:{base}-EQ")
        
        # 1. Fetch Daily History and compute ADR % and ADR Abs
        adr_val = None
        adr_abs_val = None
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            from_30d_str = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            fyers = get_fyers_client()
            if fyers:
                res_d = fyers.history({
                    "symbol": full_symbol,
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
        except Exception as e:
            pass
            
        adr_str = f"{adr_val:.2f}%" if adr_val is not None else "..."
        adr_abs_str = f"₹{adr_abs_val:.2f}" if adr_abs_val is not None else "..."

        # Fetch 5m history from Fyers (5 days back is extremely safe for 200 EMA)
        results5m = fetch_fyers_indicators(full_symbol, "5", 5)
        if results5m:
            last_r = get_last_closed_candle(results5m, 5)
            if last_r:
                p = last_r["close"]
                v = last_r["vwap"]
                e20 = last_r["ema20"]
                e50 = last_r["ema50"]
                e200 = last_r["ema200"]
                r = last_r["rsi"]
                ts = last_r["timestamp"].split(" ")[-1]
                
                trend = evaluate_fyers_trend(p, v, e20, e50, e200, r)
                
                v_str = f"{v:.2f}" if v else "..."
                e20_str = f"{e20:.2f}" if e20 else "..."
                e50_str = f"{e50:.2f}" if e50 else "..."
                e200_str = f"{e200:.2f}" if e200 else "..."
                r_str = f"{r:.2f}" if r else "..."
                
                print(f"| **{base}** | {p:.2f} | {v_str} | {trend} | {e20_str} | {e50_str} | {e200_str} | {r_str} | {adr_str} | {adr_abs_str} | {ts} |")
            else:
                print(f"| **{base}** | [ No Fyers 5M History ] | - | - | - | - | - | - | - | - | - |")
        else:
            print(f"| **{base}** | [ No Fyers 5M History ] | - | - | - | - | - | - | - | - | - |")
            
    print("\n#### [4B. Fyers 15-Minute Technical Candles (Calculated from Fyers API)]")
    print("| Ticker | Price | VWAP | Trend State | EMA(20) | EMA(50) | EMA(200) | RSI | ADR (%) | ADR (Abs) | Time |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    for base in sorted(active_bases):
        full_symbol = next((s for s in watchlist if normalize_symbol(s) == base), f"NSE:{base}-EQ")
        
        # 1. Fetch Daily History and compute ADR % and ADR Abs
        adr_val = None
        adr_abs_val = None
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            from_30d_str = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            fyers = get_fyers_client()
            if fyers:
                res_d = fyers.history({
                    "symbol": full_symbol,
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
        except Exception as e:
            pass
            
        adr_str = f"{adr_val:.2f}%" if adr_val is not None else "..."
        adr_abs_str = f"₹{adr_abs_val:.2f}" if adr_abs_val is not None else "..."

        # Fetch 15m history from Fyers (15 days back for 200 EMA)
        results15m = fetch_fyers_indicators(full_symbol, "15", 15)
        if results15m:
            last_r = get_last_closed_candle(results15m, 15)
            if last_r:
                p = last_r["close"]
                v = last_r["vwap"]
                e20 = last_r["ema20"]
                e50 = last_r["ema50"]
                e200 = last_r["ema200"]
                r = last_r["rsi"]
                ts = last_r["timestamp"].split(" ")[-1]
                
                trend = evaluate_fyers_trend(p, v, e20, e50, e200, r)
                
                v_str = f"{v:.2f}" if v else "..."
                e20_str = f"{e20:.2f}" if e20 else "..."
                e50_str = f"{e50:.2f}" if e50 else "..."
                e200_str = f"{e200:.2f}" if e200 else "..."
                r_str = f"{r:.2f}" if r else "..."
                
                print(f"| **{base}** | {p:.2f} | {v_str} | {trend} | {e20_str} | {e50_str} | {e200_str} | {r_str} | {adr_str} | {adr_abs_str} | {ts} |")
            else:
                print(f"| **{base}** | [ No Fyers 15M History ] | - | - | - | - | - | - | - | - | - |")
        else:
            print(f"| **{base}** | [ No Fyers 15M History ] | - | - | - | - | - | - | - | - | - |")

    print("\n============================================================")
    print("👉 INSTRUCTIONS FOR CLAUDE:")
    print("1. Map these indicators to your active positions queried via mcp_kite_get_positions().")
    print("2. Normalise symbol 'SBIN' with 'NSE:SBIN-EQ' (Fyers) / 'NSE:SBIN' (Zerodha).")
    print("3. CRITICAL QUANTITATIVE TREND CONFIRMATION ENGINE LOGIC:")
    print("   The 'Trend State' in the telemetry tables is evaluated using these strict rules:")
    print("   🟢 Bullish Setup (Breakout Confirmation):")
    print("     - Rule 1 (Baseline): Price > VWAP (Price is trading above institutional average price)")
    print("     - Rule 2 (Trend Structure): 20 EMA > 50 EMA (Short-term trend is above mid-term trend)")
    print("     - Rule 3 (Long-term Anchor): Price > 200 EMA (Overall macro structure is supportive)")
    print("     - Rule 4 (Momentum): RSI > 50 (Buying pressure is dominant)")
    print("   🔴 Bearish Setup (Breakdown Confirmation):")
    print("     - Rule 1 (Baseline): Price < VWAP (Price is trading below institutional average price)")
    print("     - Rule 2 (Trend Structure): 20 EMA < 50 EMA (Short-term trend is below mid-term trend)")
    print("     - Rule 3 (Long-term Anchor): Price < 200 EMA (Overall macro structure is resistive)")
    print("     - Rule 4 (Momentum): RSI < 50 (Selling pressure is dominant)")
    print("   Mapped Trend States in Telemetry Table:")
    print("     - 🟢 BULLISH: All 4 Bullish rules are met.")
    print("     - 🔴 BEARISH: All 4 Bearish rules are met.")
    print("     - ⚠️ OVERBOUGHT: All 4 Bullish rules are met, but RSI > 70 (caution on chase).")
    print("     - ⚠️ OVERSOLD: All 4 Bearish rules are met, but RSI < 30 (caution on shorting support).")
    print("     - 🟡 CONGESTION: Indicators are conflicting or sideways.")
    print("4. Actionable Directives:")
    print("   - When Trend State is 🟢 BULLISH: Look for long entries on pullbacks to the 20/50 EMAs.")
    print("   - When Trend State is 🔴 BEARISH: Look for short entries on rallies to the 20/50 EMAs.")
    print("   - When Trend State is 🟡 CONGESTION: Avoid starting new momentum trades (market is choppy).")
    print("   - When Trend State is ⚠️ OVERBOUGHT / ⚠️ OVERSOLD: Tighten trailing stops immediately.")
    print("============================================================")

if __name__ == "__main__":
    generate_telemetry()
