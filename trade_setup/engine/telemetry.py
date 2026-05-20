import os
import csv
from datetime import datetime
import pandas as pd
import config

def get_orb_range_from_logs(self, symbol):
    """
    Parses closed Fyers 15m logs to capture the first 15-minute candle range (9:15 AM - 9:30 AM).
    Guarded to only parse today's logs. Falls back to shared data/orb_ranges.json for dynamically added radar stocks.
    """
    try:
        # 1. Primary Fallback: Check shared data/orb_ranges.json populated by the dashboard Fyers history updater
        import json
        path = os.path.join("data", "orb_ranges.json")
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    shared_ranges = json.load(f)
                    key = symbol.upper()
                    if key in shared_ranges:
                        return {
                            "high": float(shared_ranges[key]["high"]),
                            "low": float(shared_ranges[key]["low"])
                        }
            except Exception as e:
                print(f"⚠️ Error reading shared ORB ranges: {e}")

        # 2. Log-based check (for pre-market watchlist symbols with active log files)
        target_symbol = f"NSE:{symbol}-EQ"
        prices = []
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        for row in self.memory_logs[config.FYERS_LOG_15M]:
            if len(row) < 3:
                continue
            if not row[0].startswith(today_str):
                continue
            # timestamp, symbol, last_price, volume, buy_qty, sell_qty
            timestamp_str, row_sym, ltp = row[0], row[1], row[2]
            
            if row_sym == target_symbol:
                try:
                    time_str = timestamp_str.split(" ")[1] if " " in timestamp_str else timestamp_str
                    t_parts = time_str.split(':')
                    hour, minute = int(t_parts[0]), int(t_parts[1])
                    if hour == 9 and 15 <= minute <= 30:
                        prices.append(float(ltp))
                except (ValueError, IndexError):
                    continue
        
        if not prices:
            return None
            
        return {"high": max(prices), "low": min(prices)}
    except Exception as e:
        print(f"⚠️ Error parsing ORB range for {symbol}: {e}")
        return None

def get_volume_baseline(self, symbol):
    """
    Calculates the Average Volume over the last 20 completed 5-minute candles of today.
    """
    try:
        target_symbol = f"NSE:{symbol}-EQ"
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        volumes = [
            float(row[3]) for row in self.memory_logs[config.FYERS_LOG_5M] 
            if len(row) >= 4 and row[1] == target_symbol and row[0].startswith(today_str)
        ]
        
        # Calculate consecutive differences to get the actual 5-minute candle volumes
        candle_volumes = []
        if volumes:
            candle_volumes.append(volumes[0])
            for i in range(1, len(volumes)):
                diff = volumes[i] - volumes[i-1]
                if diff >= 0:
                    candle_volumes.append(diff)
                else:
                    candle_volumes.append(volumes[i])
        
        recent_volumes = candle_volumes[-20:]
        if len(recent_volumes) < 5:
            return 0.0
            
        return sum(recent_volumes) / len(recent_volumes)
    except Exception as e:
        return 0.0

def get_volume_baseline_15m(self, symbol):
    """
    Calculates the Average Volume over the last 20 completed 15-minute candles of today.
    """
    try:
        target_symbol = f"NSE:{symbol}-EQ"
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        volumes = [
            float(row[3]) for row in self.memory_logs[config.FYERS_LOG_15M] 
            if len(row) >= 4 and row[1] == target_symbol and row[0].startswith(today_str)
        ]
        
        # Calculate consecutive differences to get the actual 15-minute candle volumes
        candle_volumes = []
        if volumes:
            candle_volumes.append(volumes[0])
            for i in range(1, len(volumes)):
                diff = volumes[i] - volumes[i-1]
                if diff >= 0:
                    candle_volumes.append(diff)
                else:
                    candle_volumes.append(volumes[i])
        
        recent_volumes = candle_volumes[-20:]
        if len(recent_volumes) < 5:
            return 0.0
            
        return sum(recent_volumes) / len(recent_volumes)
    except Exception as e:
        return 0.0

def get_tick_spread_volume(self, symbol):
    """
    Calculates cumulative buy and sell volume from today's raw tick logs (last 50 ticks / 1 min).
    """
    try:
        target_symbol = f"NSE:{symbol}-EQ"
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        ticks = [
            (float(row[4]), float(row[5])) for row in self.memory_logs[config.FYERS_LOG] 
            if len(row) >= 6 and row[1] == target_symbol and row[0].startswith(today_str)
        ]
        
        recent_ticks = ticks[-50:]
        if len(recent_ticks) < 10:
            return 1.0, 1.0
            
        buy_vol = sum(t[0] for t in recent_ticks)
        sell_vol = sum(t[1] for t in recent_ticks)
        return buy_vol, sell_vol
    except Exception as e:
        return 1.0, 1.0

def get_daily_open_price(self, symbol):
    """Retrieves the Daily Open price of today from raw tick logs."""
    try:
        if not os.path.exists(config.FYERS_LOG):
            return None
        today_str = datetime.now().strftime("%Y-%m-%d")
        df = pd.read_csv(config.FYERS_LOG)
        # Filter for today's rows
        df = df[df["timestamp"].str.startswith(today_str)]
        sym_df = df[df["symbol"] == f"NSE:{symbol}-EQ"]
        if sym_df.empty:
            return None
        # The first recorded price today is the daily open
        first_row = sym_df.iloc[0]
        return float(first_row["last_price"])
    except Exception as e:
        print(f"⚠️ Error parsing Daily Open for {symbol}: {e}")
        return None
