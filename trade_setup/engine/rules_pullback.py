import os
import json
from datetime import datetime
import config

def evaluate_pullback_rules(self, item):
    """Runs the pullback scan, state machine, and trigger logic for a radar stock."""
    symbol = item["symbol"]
    direction = item["direction"]
    spike_price = float(item["spike_price"])
    spike_open = float(item.get("spike_open", spike_price))
    spike_time = item["spike_time"]
    state = item.get("state", "WAITING_FOR_PULLBACK")

    base_symbol = symbol.replace("NSE:", "").replace("-EQ", "").upper()

    # 1. Fetch indicators logs
    symbol_rows = []
    if config.FYERS_INDICATORS_5M in self.memory_logs:
        for row in self.memory_logs[config.FYERS_INDICATORS_5M]:
            if len(row) < 11:
                continue
            sym = row[1]
            row_ticker = sym.split(":")[1].split("-EQ")[0] if ":" in sym else sym
            if row_ticker == base_symbol or sym == symbol:
                p_val = float(row[2])
                symbol_rows.append({
                    "timestamp": row[0],
                    "price": p_val,
                    "ema20": float(row[3]) if row[3] else 0.0,
                    "ema50": float(row[4]) if row[4] else 0.0,
                    "ema200": float(row[5]) if row[5] else 0.0,
                    "rsi": float(row[6]) if row[6] else 0.0,
                    "vwap": float(row[7]) if row[7] else 0.0,
                    "volume": float(row[8]) if row[8] else 0.0,
                    "high": float(row[11]) if len(row) > 11 and row[11] else p_val,
                    "low": float(row[12]) if len(row) > 12 and row[12] else p_val
                })

    if not symbol_rows:
        return "WAITING - No indicators telemetry found in logs."

    latest_indicators = symbol_rows[-1]
    
    # 2. Live Price Check
    price = latest_indicators["price"]
    if not self.dry_run and self.kite:
        try:
            ltp_res = self.kite.ltp(f"NSE:{base_symbol}")
            price = float(ltp_res[f"NSE:{base_symbol}"]["last_price"])
        except Exception as e:
            print(f"⚠️ Failed to fetch live price from Kite for {base_symbol}: {e}")

    # 3. Market Time Guard
    now = datetime.now().time()
    market_live = now >= datetime.strptime("09:30:00", "%H:%M:%S").time()
    if not market_live:
        return "WAITING - Market open range lock pending."
        
    if now >= datetime.strptime("15:00:00", "%H:%M:%S").time():
        return "FAILED - Past 3:00 PM. Removing from watchlist."

    # 4. ORB Range Check
    if base_symbol not in self.orb_ranges:
        orb = self.get_orb_range_from_logs(base_symbol)
        if not orb:
            return "WAITING - Missing morning 15m logs for ORB."
        self.orb_ranges[base_symbol] = orb

    orb_high = float(self.orb_ranges[base_symbol]["high"])
    orb_low = float(self.orb_ranges[base_symbol]["low"])

    # 5. Extract completed pullback candles
    # Pullback candles are closed candles with timestamp strictly after spike_time
    try:
        spike_dt = datetime.strptime(spike_time, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            spike_dt = datetime.strptime(spike_time, "%H:%M:%S")
            # Set today's date if only time was logged
            today = datetime.now()
            spike_dt = spike_dt.replace(year=today.year, month=today.month, day=today.day)
        except Exception:
            spike_dt = datetime.now()

    pullback_candles = []
    for r in symbol_rows:
        try:
            row_dt = datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S")
            if row_dt > spike_dt:
                pullback_candles.append(r)
        except Exception:
            pass

    # Update pullback high/low memory
    completed_pullback_low = item.get("pullback_low")
    completed_pullback_high = item.get("pullback_high")

    for candle in pullback_candles:
        # For long: track lowest price printed
        if completed_pullback_low is None or candle["low"] < completed_pullback_low:
            completed_pullback_low = candle["low"]
        # For short: track highest price printed
        if completed_pullback_high is None or candle["high"] > completed_pullback_high:
            completed_pullback_high = candle["high"]

    # Save values back to watchlist item to persist across iterations
    item["pullback_low"] = completed_pullback_low
    item["pullback_high"] = completed_pullback_high

    # 6. Evaluate Strategy Rules
    if direction == "BUY":
        # Invalidation Check: close of any pullback candle below ORB High or Spike Open or VWAP
        if pullback_candles:
            last_closed = pullback_candles[-1]
            if last_closed["price"] < orb_high or last_closed["price"] < spike_open or last_closed["price"] < last_closed["vwap"]:
                print(f"🛑 [INVALIDATE-BUY] {base_symbol} closed below breakout bounds (Close: {last_closed['price']} | ORB High: {orb_high} | Spike Open: {spike_open} | VWAP: {last_closed['vwap']})")
                return "INVALIDATED"

        # State Transition: Wait until price has dropped below EMA20 (entered pullback corridor)
        ema20 = latest_indicators["ema20"]
        vwap = latest_indicators["vwap"]
        
        if state == "WAITING_FOR_PULLBACK":
            if price <= ema20:
                item["state"] = "IN_PULLBACK"
                state = "IN_PULLBACK"
                print(f"🔄 [STATE-CHANGE] {base_symbol} entered Pullback Zone (Price: {price} <= EMA20: {ema20})")
            else:
                return f"WAITING - Price ({price}) still above EMA20 ({ema20})"

        # Volume Drying Check
        avg_vol_5m = self.get_volume_baseline(base_symbol)
        if avg_vol_5m > 0:
            for candle in pullback_candles:
                if candle["volume"] >= 0.8 * avg_vol_5m:
                    return f"WAITING - Volume ({candle['volume']}) not contracting (0.8x Baseline: {0.8 * avg_vol_5m:.0f})"

        # Reversal Trigger check
        if not pullback_candles:
            return "WAITING - Waiting for first pullback candle to close."
            
        # Determine the trigger candle: last closed candle (or second-to-last if price is fallback close of last)
        if len(pullback_candles) >= 2 and abs(price - pullback_candles[-1]["price"]) < 0.0001:
            trigger_candle = pullback_candles[-2]
        else:
            trigger_candle = pullback_candles[-1]
            
        trigger_line = trigger_candle["high"] # Trigger on breaking high of previous 5m candle
        
        # Pullback lowest point calculation for SL
        current_low = completed_pullback_low if completed_pullback_low is not None else price
        
        if price > trigger_line:
            # TRIGGER LONG ENTRY!
            print(f"🎯 [TRIGGER-PULLBACK-BUY] {base_symbol} trigger fired at {price} (broke trigger: {trigger_line})")
            self.execute_radar_buy_disciplines(base_symbol, price, current_low, orb_high)
            return "🟢 CONVERGENCE PERFECT - PULLBACK BUY TRIGGERED"
        else:
            return f"WAITING - In pullback zone. Price ({price}) needs to break above trigger line ({trigger_line})"

    else: # direction == "SELL"
        # Invalidation Check: close of any pullback candle above ORB Low or Spike Open or VWAP
        if pullback_candles:
            last_closed = pullback_candles[-1]
            if last_closed["price"] > orb_low or last_closed["price"] > spike_open or last_closed["price"] > last_closed["vwap"]:
                print(f"🛑 [INVALIDATE-SELL] {base_symbol} closed above breakdown bounds (Close: {last_closed['price']} | ORB Low: {orb_low} | Spike Open: {spike_open} | VWAP: {last_closed['vwap']})")
                return "INVALIDATED"

        # State Transition: Wait until price has bounced above EMA20 (entered pullback corridor)
        ema20 = latest_indicators["ema20"]
        vwap = latest_indicators["vwap"]

        if state == "WAITING_FOR_PULLBACK":
            if price >= ema20:
                item["state"] = "IN_PULLBACK"
                state = "IN_PULLBACK"
                print(f"🔄 [STATE-CHANGE] {base_symbol} entered Pullback Zone (Price: {price} >= EMA20: {ema20})")
            else:
                return f"WAITING - Price ({price}) still below EMA20 ({ema20})"

        # Volume Drying Check
        avg_vol_5m = self.get_volume_baseline(base_symbol)
        if avg_vol_5m > 0:
            for candle in pullback_candles:
                if candle["volume"] >= 0.8 * avg_vol_5m:
                    return f"WAITING - Volume ({candle['volume']}) not contracting (0.8x Baseline: {0.8 * avg_vol_5m:.0f})"

        # Reversal Trigger check
        if not pullback_candles:
            return "WAITING - Waiting for first pullback candle to close."

        # Determine the trigger candle: last closed candle (or second-to-last if price is fallback close of last)
        if len(pullback_candles) >= 2 and abs(price - pullback_candles[-1]["price"]) < 0.0001:
            trigger_candle = pullback_candles[-2]
        else:
            trigger_candle = pullback_candles[-1]
            
        trigger_line = trigger_candle["low"] # Trigger on breaking low of previous 5m candle
        
        # Pullback highest point calculation for SL
        current_high = completed_pullback_high if completed_pullback_high is not None else price

        if price < trigger_line:
            # TRIGGER SHORT ENTRY!
            print(f"🎯 [TRIGGER-PULLBACK-SELL] {base_symbol} trigger fired at {price} (broke trigger: {trigger_line})")
            self.execute_radar_sell_disciplines(base_symbol, price, current_high, orb_low)
            return "🟢 CONVERGENCE PERFECT - PULLBACK SELL TRIGGERED"
        else:
            return f"WAITING - In pullback zone. Price ({price}) needs to break below trigger line ({trigger_line})"
