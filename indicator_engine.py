import math
from datetime import datetime

def calculate_ema(closes, period):
    """Calculates Exponential Moving Average (EMA)."""
    if len(closes) < period:
        return [None] * len(closes)
    
    ema = [None] * len(closes)
    # Use SMA as the initial value for the first EMA
    sma = sum(closes[:period]) / period
    ema[period - 1] = sma
    
    alpha = 2.0 / (period + 1)
    for i in range(period, len(closes)):
        prev = ema[i - 1]
        if prev is None:
            prev = sma
        ema[i] = (closes[i] * alpha) + (prev * (1.0 - alpha))
        
    return ema

def calculate_vwap(candles):
    """Calculates Volume Weighted Average Price (VWAP) resetting daily.
    candles: list of [timestamp, open, high, low, close, volume]
    """
    vwap = [None] * len(candles)
    
    # Track daily cumulative variables
    current_day = None
    cum_pv = 0.0
    cum_vol = 0.0
    
    for i, c in enumerate(candles):
        ts, o, h, l, cl, vol = c
        
        # Convert timestamp to date to detect daily rollover (India/Kolkata is +5:30)
        dt = datetime.fromtimestamp(ts)
        day_str = dt.strftime("%Y-%m-%d")
        
        if day_str != current_day:
            # Daily reset
            current_day = day_str
            cum_pv = 0.0
            cum_vol = 0.0
            
        typical_price = (h + l + cl) / 3.0
        cum_pv += typical_price * vol
        cum_vol += vol
        
        if cum_vol > 0:
            vwap[i] = cum_pv / cum_vol
        else:
            vwap[i] = typical_price
            
    return vwap

def calculate_rsi(closes, period=14):
    """Calculates Wilder's Relative Strength Index (RSI)."""
    if len(closes) <= period:
        return [None] * len(closes)
        
    rsi_values = [None] * len(closes)
    
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(0.0, diff))
        losses.append(max(0.0, -diff))
        
    # First Average Gain and Average Loss (SMA of first 'period' gains/losses)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    if avg_loss == 0:
        rs = 99999.0
    else:
        rs = avg_gain / avg_loss
    rsi_values[period] = 100.0 - (100.0 / (1.0 + rs))
    
    # Wilder's smoothing technique
    for i in range(period + 1, len(closes)):
        gain = gains[i - 1]
        loss = losses[i - 1]
        
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        
        if avg_loss == 0:
            rsi = 100.0 if avg_gain > 0 else 50.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))
        rsi_values[i] = rsi
        
    return rsi_values

def compute_indicators(candles):
    """Takes Fyers candles and computes all indicators.
    candles: list of [timestamp, open, high, low, close, volume]
    Returns a list of dictionaries with calculated technical states.
    """
    if not candles:
        return []
        
    closes = [c[4] for c in candles]
    
    # Calculations
    ema20 = calculate_ema(closes, 20)
    ema50 = calculate_ema(closes, 50)
    ema200 = calculate_ema(closes, 200)
    vwap = calculate_vwap(candles)
    rsi = calculate_rsi(closes, 14)
    
    results = []
    for i, c in enumerate(candles):
        ts, o, h, l, cl, vol = c
        dt_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        results.append({
            "timestamp": dt_str,
            "epoch": ts,
            "open": o,
            "high": h,
            "low": l,
            "close": cl,
            "volume": vol,
            "ema20": ema20[i],
            "ema50": ema50[i],
            "ema200": ema200[i],
            "vwap": vwap[i],
            "rsi": rsi[i]
        })
        
    return results

def calculate_adr_percentage(daily_candles, period=14):
    """Calculates the Average Daily Range (ADR) as a percentage over the specified period.
    daily_candles: list of [timestamp, open, high, low, close, volume] representing daily candles.
    """
    if len(daily_candles) < period:
        period = len(daily_candles)
    if period == 0:
        return 0.0
        
    ranges = []
    # Take the last 'period' completed daily daily_candles
    for c in daily_candles[-period:]:
        h, l = c[2], c[3]
        if l > 0:
            pct_range = ((h - l) / l) * 100.0
            ranges.append(pct_range)
            
    if not ranges:
        return 0.0
    return sum(ranges) / len(ranges)

def calculate_adr_absolute(daily_candles, period=14):
    """Calculates the Average Daily Range (ADR) as an absolute price difference (High - Low) over the specified period.
    daily_candles: list of [timestamp, open, high, low, close, volume] representing daily candles.
    """
    if len(daily_candles) < period:
        period = len(daily_candles)
    if period == 0:
        return 0.0
        
    ranges = []
    for c in daily_candles[-period:]:
        h, l = c[2], c[3]
        ranges.append(h - l)
        
    if not ranges:
        return 0.0
    return sum(ranges) / len(ranges)


