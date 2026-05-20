from datetime import datetime
import config

def evaluate_live_rules(self, symbol):
    """Runs the sequential intraday checks for a watchlist stock."""
    # 1. Fetch live telemetry metrics calculated by indicator_engine.py
    try:
        latest_row = None
        all_symbol_rows = []
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # Map indices: timestamp(0), symbol(1), price(2), ema20(3), ema50(4), ema200(5), rsi(6), vwap(7), volume(8), adr(9), adr_abs(10)
        for row in self.memory_logs[config.FYERS_INDICATORS_5M]:
            if len(row) < 11:
                continue
            if not row[0].startswith(today_str):
                continue
            sym = row[1]
            row_ticker = sym.split(":")[1].split("-EQ")[0] if ":" in sym else sym
            if row_ticker == symbol or sym == symbol:
                mapped_row = {
                    "timestamp": row[0],
                    "price": row[2],
                    "ema20": row[3],
                    "ema50": row[4],
                    "ema200": row[5],
                    "rsi": row[6],
                    "vwap": row[7],
                    "volume": row[8],
                    "adr": row[9]
                }
                latest_row = mapped_row
                all_symbol_rows.append(mapped_row)
        
        if not latest_row:
            return None
            
        price = float(latest_row["price"])
        vwap = float(latest_row["vwap"])
        ema20 = float(latest_row["ema20"])
        ema50 = float(latest_row["ema50"])
        ema200 = float(latest_row["ema200"])
        rsi = float(latest_row["rsi"])
        adr_pct = float(latest_row["adr"])
        latest = latest_row
    except Exception as e:
        return None

    # Check 1: Establish morning ORB range (9:15 - 9:30)
    now = datetime.now().time()
    market_live = now >= datetime.strptime("09:30:00", "%H:%M:%S").time()
    
    if not market_live:
        return f"Waiting for 09:30 AM range lock."
        
    # Entry Time Guard: Block new entries after 15:00:00 (3:00 PM) to protect capital
    if now >= datetime.strptime("15:00:00", "%H:%M:%S").time():
        return f"FAILED - Current time ({now.strftime('%H:%M:%S')}) is past 3:00 PM. New entries blocked."
        
    if symbol not in self.orb_ranges:
        orb = self.get_orb_range_from_logs(symbol)
        if not orb:
            return f"Missing 15m Morning logs to construct ORB range."
        self.orb_ranges[symbol] = orb
        print(f"🎯 Range locked for {symbol} | 15m High: {orb['high']} | 15m Low: {orb['low']}")

    orb_high = self.orb_ranges[symbol]["high"]
    orb_low = self.orb_ranges[symbol]["low"]

    # Check 2: Intraday VWAP Anchor
    if price <= vwap:
        return f"FAILED - Price ({price}) is below VWAP ({vwap})"

    # Check 3: Intraday EMA Alignment
    if not (ema20 > ema50 and price > ema200):
        return f"FAILED - EMA structure not aligned (EMA20: {ema20}, EMA50: {ema50}, Price: {price})"

    # Check 4: RSI Momentum Guard
    if rsi < 50 or rsi > 70:
        return f"FAILED - RSI ({rsi}) not in neutral-bullish range (50-70)"

    # Check 5: The Breakout Trigger
    if price <= orb_high:
        return f"FAILED - Price ({price}) has not broken above 15m High ({orb_high})"

    # Check 6: Breakout Volume Expansion (1.5x of 15m clock-aligned baseline)
    ts_str = latest.get("timestamp", "")
    dt_val = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    minute = dt_val.minute
    elapsed_5m_candles = (minute % 15) // 5 + 1
    
    # Calculate block start string (e.g. 10:00:00 for 10:10:00)
    dt_block_start = dt_val.replace(minute=minute - minute % 15, second=0, microsecond=0)
    block_start_str = dt_block_start.strftime("%Y-%m-%d %H:%M:%S")
    
    # Sum volume of completed 5m candles in this official 15m block
    current_block_vol = 0.0
    for r in all_symbol_rows:
        r_ts = r.get("timestamp", "")
        if r_ts >= block_start_str and r_ts <= ts_str:
            current_block_vol += float(r.get("volume", 0))
            
    # Calculate 15m volume baseline from 15m closed candle logs
    avg_vol_15m = self.get_volume_baseline_15m(symbol)
    
    if avg_vol_15m > 0:
        target_vol = 0.5 * elapsed_5m_candles * avg_vol_15m
        if current_block_vol < target_vol:
            return f"FAILED - Breakout on low cumulative 15m volume ({current_block_vol:.0f} vs Clock-Proportional Target: {target_vol:.0f} | Elapsed 5m candles: {elapsed_5m_candles}/3)"
    else:
        # Fallback to 5m baseline as safety check if 15m log is empty
        avg_vol_5m = self.get_volume_baseline(symbol)
        latest_vol = float(latest.get("volume", 0))
        if avg_vol_5m > 0 and latest_vol < (avg_vol_5m * 1.5):
            return f"FAILED - Breakout on low 5m volume ({latest_vol:.0f} vs 1.5x Avg: {avg_vol_5m * 1.5:.0f})"

    # Check 7: Micro Tick Spread Skew (1.15x buyer dominance over last 50 ticks)
    buy_vol, sell_vol = self.get_tick_spread_volume(symbol)
    if sell_vol > 0:
        ratio = buy_vol / sell_vol
        if ratio < 1.15:
            return f"FAILED - Tick spread skew not dominant (Buyer/Seller Ratio: {ratio:.2f} < 1.15)"
    else:
        ratio = 1.0

    # All Gates Passed -> TRIGGER BUY!
    self.execute_order_disciplines(symbol, price, orb_low)
    return "🟢 CONVERGENCE PERFECT - BUY TRIGGERED"
