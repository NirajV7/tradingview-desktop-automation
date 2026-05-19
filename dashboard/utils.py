import os
import json
import config
from fastapi.responses import RedirectResponse, JSONResponse
from urllib.parse import quote_plus

def load_watchlist():
    """Utility helper to load watchlist dict {"buy": [], "sell": []}."""
    data = {"buy": [], "sell": []}
    if os.path.exists(config.WATCHLIST_FILE):
        try:
            with open(config.WATCHLIST_FILE, "r") as f:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    data["buy"] = loaded
                elif isinstance(loaded, dict):
                    data["buy"] = loaded.get("buy", [])
                    data["sell"] = loaded.get("sell", [])
        except Exception as e:
            print(f"Error loading watchlist: {e}")
    return data

def make_response(msg: str, msg_type: str, ajax: bool = False):
    if ajax:
        return JSONResponse({"status": "success" if msg_type == "success" else "error", "message": msg})
    return RedirectResponse(url=f"/?msg={quote_plus(msg)}&msg_type={msg_type}", status_code=303)

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
                return "⚠️ OVERBOUGHT", "trend-bull"
            return "🟢 BULLISH", "trend-bull"
            
        if is_bear_baseline and is_bear_structure and is_bear_anchor and is_bear_momentum:
            if r < 30:
                return "⚠️ OVERSOLD", "trend-bear"
            return "🔴 BEARISH", "trend-bear"
            
        return "🟡 CONGESTION", "trend-neut"
    except:
        return "🟡 CONGESTION", "trend-neut"

def get_trend_dot_style(state):
    if "BULLISH" in state:
        return "background: #3fb950; box-shadow: 0 0 10px #3fb950, inset 0 0 2px rgba(255,255,255,0.6);"
    elif "BEARISH" in state:
        return "background: #f85149; box-shadow: 0 0 10px #f85149, inset 0 0 2px rgba(255,255,255,0.6);"
    elif "OVERBOUGHT" in state:
        return "background: #3fb950; box-shadow: 0 0 12px #58a6ff; border: 1.5px solid #58a6ff;"
    elif "OVERSOLD" in state:
        return "background: #f85149; box-shadow: 0 0 12px #ff7b72; border: 1.5px solid #ff7b72;"
    elif "CONGESTION" in state:
        return "background: #d29922; box-shadow: 0 0 10px #d29922, inset 0 0 2px rgba(255,255,255,0.6);"
    else:
        return "background: #8b949e; box-shadow: 0 0 6px #8b949e;"

def format_sub_metrics(price, vwap, rsi):
    try:
        p = float(price)
        v = float(vwap)
        r = float(rsi)
        
        dist = ((p - v) / v) * 100
        sign = "+" if dist >= 0 else ""
        dist_color = "#3fb950" if dist >= 0 else "#f85149"
        
        return f"""
        <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.8em; color: #8b949e; line-height: 1.4; text-align: center; margin-bottom: 2px;">
            <span style="color: #c9d1d9;">RSI {r:.1f}</span><br>
            <span style="color: {dist_color}; font-size: 0.9em; font-weight: 600;">{sign}{dist:.2f}%</span>
        </div>
        """
    except:
        return """
        <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.8em; color: #8b949e; line-height: 1.4; text-align: center; margin-bottom: 2px;">
            <span style="color: #8b949e;">RSI --</span><br>
            <span style="color: #8b949e; font-size: 0.9em;">0.00%</span>
        </div>
        """
