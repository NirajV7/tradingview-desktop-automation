from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import json
import csv
import requests
import websocket
import random
import time
import subprocess
from datetime import datetime
import uvicorn
from urllib.parse import quote_plus

import config
import auth_manager
import sys_ops

app = FastAPI(title="NJ Quant Terminal")

# Ensure required folders exist
os.makedirs(os.path.join(config.CWD, "static/css"), exist_ok=True)
os.makedirs(os.path.join(config.CWD, "templates"), exist_ok=True)

# Mount static and templates using absolute paths to avoid resolution errors
app.mount("/static", StaticFiles(directory=os.path.join(config.CWD, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(config.CWD, "templates"))

def load_watchlist():
    """Utility helper to load watchlist array."""
    symbols_list = []
    if os.path.exists(config.WATCHLIST_FILE):
        try:
            with open(config.WATCHLIST_FILE, "r") as f:
                symbols_list = json.load(f)
        except Exception as e:
            print(f"Error loading watchlist: {e}")
    return symbols_list

# -------------------------------------------------------------
# CORE WEB ROUTES
# -------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, msg: str = None, msg_type: str = "success"):
    needs_login, auth_url = auth_manager.check_auth()
    symbols_list = load_watchlist()
    
    current_symbols_text = ", ".join([s.split(":")[1].split("-")[0] if ":" in s else s for s in symbols_list])
    
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request, 
            "needs_login": needs_login, 
            "auth_url": auth_url,
            "symbols_list": symbols_list,
            "current_symbols": current_symbols_text,
            "msg": msg,
            "msg_type": msg_type
        }
    )

@app.post("/auth")
async def auth(auth_code: str = Form(...)):
    success, message = auth_manager.exchange_token(auth_code.strip())
    if success:
        return RedirectResponse(url="/?msg=Authorized+Successfully&msg_type=success", status_code=303)
    else:
        return RedirectResponse(url=f"/?msg={quote_plus(message)}&msg_type=error", status_code=303)

@app.get("/clear_watchlist")
async def clear_watchlist():
    with open(config.WATCHLIST_FILE, "w") as f:
        json.dump([], f)
    return RedirectResponse(url="/?msg=Watchlist+Cleared&msg_type=success", status_code=303)

# -------------------------------------------------------------
# ENGINE CONTROLS & OS SYSTEM ACTIONS
# -------------------------------------------------------------

def make_response(msg: str, msg_type: str, ajax: bool = False):
    if ajax:
        return JSONResponse({"status": "success" if msg_type == "success" else "error", "message": msg})
    return RedirectResponse(url=f"/?msg={quote_plus(msg)}&msg_type={msg_type}", status_code=303)

@app.get("/start_tv")
async def start_tv(ajax: bool = False):
    try:
        response = requests.get(config.CDP_URL, timeout=0.5)
        if response.status_code == 200:
            return make_response("TradingView is ALREADY OPEN on Port 9222", "error", ajax)
    except:
        pass # Port is free, proceed with launch

    subprocess.run('open -a "TradingView" --args --remote-debugging-port=9222', shell=True)
    return make_response("TradingView Launch Command Sent", "success", ajax)

@app.get("/stop_tv")
async def stop_tv(ajax: bool = False):
    try:
        subprocess.run("pkill -f TradingView", shell=True)
        return make_response("TradingView Closed Successfully", "success", ajax)
    except Exception as e:
        return make_response(f"Failed to close TradingView: {str(e)}", "error", ajax)

@app.get("/start_fyers")
async def start_fyers(ajax: bool = False):
    if sys_ops.is_running("fyers_official_logger.py"):
        return make_response("Fyers Engine is ALREADY RUNNING", "error", ajax)
    else:
        with open(config.ENGINE_LOG, "a") as log_file:
            subprocess.Popen(
                [config.VENV_PYTHON, os.path.join(config.CWD, "fyers_official_logger.py")], 
                cwd=config.CWD, 
                stdout=log_file, 
                stderr=log_file
            )
        return make_response("Fyers Engine Started", "success", ajax)

@app.get("/stop_fyers")
async def stop_fyers(ajax: bool = False):
    if not sys_ops.is_running("fyers_official_logger.py"):
        return make_response("Fyers Engine is already Stopped", "error", ajax)
    subprocess.run("pkill -f fyers_official_logger.py", shell=True)
    return make_response("Fyers Engine Stopped Successfully", "success", ajax)

@app.get("/start_tv_log")
async def start_tv_log(ajax: bool = False):
    if sys_ops.is_running("fetch_price.py"):
        return make_response("TV Scraper is ALREADY RUNNING", "error", ajax)
    else:
        with open(config.ENGINE_LOG, "a") as log_file:
            subprocess.Popen(
                [config.VENV_PYTHON, os.path.join(config.CWD, "fetch_price.py")], 
                cwd=config.CWD, 
                stdout=log_file, 
                stderr=log_file
            )
        return make_response("TradingView Price Scraper Started", "success", ajax)

@app.get("/stop_tv_log")
async def stop_tv_log(ajax: bool = False):
    if not sys_ops.is_running("fetch_price.py"):
        return make_response("TV Scraper is already Stopped", "error", ajax)
    subprocess.run("pkill -f fetch_price.py", shell=True)
    return make_response("TradingView Price Scraper Stopped Successfully", "success", ajax)

@app.get("/clear_logs")
async def clear_logs():
    targets = [
        config.TRADING_LOG,
        config.TRADING_LOG_5M,
        config.TRADING_LOG_15M,
        config.FYERS_LOG,
        config.FYERS_LOG_5M,
        config.FYERS_LOG_15M,
        config.ENGINE_LOG
    ]
    wiped_count = 0
    for f in targets:
        if os.path.exists(f):
            try:
                os.remove(f)
                wiped_count += 1
            except:
                pass
    return RedirectResponse(url=f"/?msg=Wiped+{wiped_count}+Active+Log+Files!&msg_type=success", status_code=303)

@app.get("/sync_tabs")
async def sync_tabs():
    symbols_list = load_watchlist()
    if not symbols_list: 
        return RedirectResponse(url="/?msg=Watchlist+is+empty&msg_type=error", status_code=303)

    try:
        response = requests.get(config.CDP_URL, timeout=1.0)
        tabs = [t for t in response.json() if "tradingview.com/chart" in t.get("url", "")]
        if not tabs: 
            return RedirectResponse(url="/?msg=No+active+TradingView+chart+found.+Open+one+manually+first.&msg_type=error", status_code=303)
        
        # 1. Scan existing tabs for (Symbol, Interval) pairs
        open_pairs = []
        for t in tabs:
            sym, interval = sys_ops.get_tab_info(t.get("webSocketDebuggerUrl"))
            if sym != "UNKNOWN":
                open_pairs.append((sym, str(interval)))
        
        # 2. Open missing intervals (5 and 15)
        target_tab_ws = tabs[0].get("webSocketDebuggerUrl")
        ws = websocket.create_connection(target_tab_ws, suppress_origin=True, timeout=5)
        
        count = 0
        target_intervals = ["5", "15"]
        
        for full_sym in symbols_list:
            clean_s = full_sym.split(":")[-1].split("-")[0].upper()
            
            for tf in target_intervals:
                if (clean_s, tf) in open_pairs:
                    continue
                    
                # Open specific Symbol + Interval
                base_sym = full_sym.split('-')[0]
                target_url = f"https://in.tradingview.com/chart/?symbol={base_sym}&interval={tf}"
                js_command = f"window.open('{target_url}', '_blank');"
                
                payload = {
                    "id": random.randint(1, 10000),
                    "method": "Runtime.evaluate",
                    "params": {"expression": js_command}
                }
                ws.send(json.dumps(payload))
                count += 1
                time.sleep(1.5) # Prevent browser request blocking
        
        ws.close()
        if count > 0:
            return RedirectResponse(url=f"/?msg=Opened+{count}+Dual-Timeframe+Tabs&msg_type=success", status_code=303)
        else:
            return RedirectResponse(url="/?msg=All+5m/15m+Pairs+Already+Open&msg_type=success", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/?msg=Sync+Failed:+{quote_plus(str(e))}&msg_type=error", status_code=303)

@app.get("/start_all")
async def start_all(ajax: bool = False):
    launched = 0
    
    # 1. TradingView app
    tv_running = False
    try:
        res = requests.get(config.CDP_URL, timeout=0.5)
        if res.status_code == 200:
            tv_running = True
    except:
        pass
    if not tv_running:
        subprocess.run('open -a "TradingView" --args --remote-debugging-port=9222', shell=True)
        launched += 1
        time.sleep(1.0)
        
    # 2. Fyers
    if not sys_ops.is_running("fyers_official_logger.py"):
        with open(config.ENGINE_LOG, "a") as log_file:
            subprocess.Popen(
                [config.VENV_PYTHON, os.path.join(config.CWD, "fyers_official_logger.py")], 
                cwd=config.CWD, 
                stdout=log_file, 
                stderr=log_file
            )
        launched += 1
        
    # 3. TV Price Logs scraper
    if not sys_ops.is_running("fetch_price.py"):
        with open(config.ENGINE_LOG, "a") as log_file:
            subprocess.Popen(
                [config.VENV_PYTHON, os.path.join(config.CWD, "fetch_price.py")], 
                cwd=config.CWD, 
                stdout=log_file, 
                stderr=log_file
            )
        launched += 1
        
    if launched > 0:
        return make_response(f"Successfully Started {launched} Stopped Components", "success", ajax)
    return make_response("All System Engines are already Active", "error", ajax)

@app.get("/stop")
async def stop(ajax: bool = False):
    stopped = 0
    with open(config.ENGINE_LOG, "a") as log_file:
        log_file.write(f"[{datetime.now().strftime('%H:%M:%S')}] 🛑 STOP ALL COMMAND RECEIVED...\n")
        
    if sys_ops.is_running("fyers_official_logger.py"):
        subprocess.run("pkill -f fyers_official_logger.py", shell=True)
        stopped += 1
    if sys_ops.is_running("fetch_price.py"):
        subprocess.run("pkill -f fetch_price.py", shell=True)
        stopped += 1
        

    with open(config.ENGINE_LOG, "a") as log_file:
        log_file.write(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ System shutdown complete. {stopped} engines killed.\n")

    if stopped > 0:
        return make_response(f"Successfully Stopped {stopped} Components", "success", ajax)
    return make_response("All Components were already Stopped", "error", ajax)

# -------------------------------------------------------------
# REST TELEMETRY & AJAX API CHANNELS
# -------------------------------------------------------------

@app.get("/api/search")
async def search(q: str = ""):
    query = q.upper()
    if not query:
        return JSONResponse([])
    
    results = []
    for s in config.MASTER_SYMBOLS:
        if query in s['ticker'] or query in s['name']:
            results.append(s)
        if len(results) >= 10: 
            break
    return JSONResponse(results)

@app.post("/api/add_symbol")
async def add_symbol(request: Request):
    data = await request.json()
    symbol = data.get('symbol')
    
    symbols_list = load_watchlist()
    
    if symbol and symbol not in symbols_list:
        symbols_list.append(symbol)
        with open(config.WATCHLIST_FILE, "w") as f:
            json.dump(symbols_list, f)
            
    return JSONResponse({"status": "ok"})

@app.post("/api/remove_symbol")
async def remove_symbol(request: Request):
    data = await request.json()
    symbol = data.get('symbol')
    
    symbols_list = load_watchlist()
    
    if symbol in symbols_list:
        symbols_list.remove(symbol)
        with open(config.WATCHLIST_FILE, "w") as f:
            json.dump(symbols_list, f)
            
    return JSONResponse({"status": "ok"})

@app.get("/api/status")
async def api_status():
    tv_open = False
    try:
        res = requests.get(config.CDP_URL, timeout=0.5)
        if res.status_code == 200:
            # Robust Check: Ensure at least one tab is actually a TradingView chart
            tabs = res.json()
            tv_open = any("tradingview.com/chart" in t.get("url", "") for t in tabs)
    except: 
        pass
    
    return JSONResponse({
        "tv": tv_open,
        "fyers": sys_ops.is_running("fyers_official_logger.py"),
        "log": sys_ops.is_running("fetch_price.py")
    })

@app.get("/api/logs")
async def api_logs():
    if not os.path.exists(config.ENGINE_LOG):
        return JSONResponse({"logs": ""})
    try:
        if os.path.getsize(config.ENGINE_LOG) > 1024 * 1024:
            with open(config.ENGINE_LOG, "w") as f:
                f.write(f"[{datetime.now().strftime('%H:%M:%S')}] ♻️ Log Rotated (Size exceeded 1MB)\n")
        
        with open(config.ENGINE_LOG, "r") as f:
            lines = f.readlines()
            last_lines = "".join(lines[-20:])
            return JSONResponse({"logs": last_lines})
    except:
        return JSONResponse({"logs": "Error reading logs..."})

@app.get("/api/data")
async def api_data():
    active_symbols = load_watchlist()
    active_names = [s.split(":")[1].split("-")[0] if ":" in s else s for s in active_symbols]
    data_map = {}

    # 1. Parse official logs (LTP)
    if os.path.exists(config.FYERS_LOG):
        try:
            with open(config.FYERS_LOG, "r") as f:
                lines = f.readlines()
                if len(lines) > 1:
                    reader = csv.DictReader(lines)
                    for row in reader:
                        sym = row.get('symbol', '')
                        name = sym.split(":")[1].split("-")[0] if ":" in sym else sym
                        if name in active_names:
                            if name not in data_map: 
                                data_map[name] = {}
                            data_map[name]['lp'] = row.get('last_price', '...')
        except: 
            pass

    # 2. Parse Technical Price logs (VWAPs, indicator levels)
    if os.path.exists(config.TRADING_LOG):
        try:
            with open(config.TRADING_LOG, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row.get('symbol')
                    if name in active_names:
                        if name not in data_map: 
                            data_map[name] = {}
                        tf = str(row.get('timeframe'))
                        data_map[name][tf] = row.get('price')
                        
                        for col_key, val in row.items():
                            if val is None or val == "":
                                continue
                            k = col_key.lower()
                            if "vwap" in k or "volume weighted average price" in k:
                                data_map[name][f"{tf}_vwap"] = val
                            elif "exponential(200)" in k or k == "ind_moving average exponential":
                                data_map[name][f"{tf}_ema200"] = val
                            elif "exponential(50)" in k or "moving average exponential 2" in k:
                                data_map[name][f"{tf}_ema50"] = val
                            elif "exponential(20)" in k or "moving average exponential 3" in k:
                                data_map[name][f"{tf}_ema20"] = val
                            elif "rsi" in k or "relative strength index" in k:
                                data_map[name][f"{tf}_rsi"] = val
        except: 
            pass

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

    # Render HTML Rows
    html = ""
    for name in active_names:
        d = data_map.get(name, {})
        p5 = d.get('5', '...')
        p15 = d.get('15', '...')
        lp = d.get('lp', '...')
        
        # 5m Trend State
        trend5, class5 = "WAITING", "trend-neut"
        if p5 != '...':
            trend5, class5 = evaluate_trend_state(
                p5, d.get('5_vwap'), d.get('5_ema20'), d.get('5_ema50'), d.get('5_ema200'), d.get('5_rsi')
            )
            
        # 15m Trend State
        trend15, class15 = "WAITING", "trend-neut"
        if p15 != '...':
            trend15, class15 = evaluate_trend_state(
                p15, d.get('15_vwap'), d.get('15_ema20'), d.get('15_ema50'), d.get('15_ema200'), d.get('15_rsi')
            )
            
        # Overall Confluence Trend Signal
        conf = "🟡 CONGESTION"
        badge_class = "trend-neut"
        
        is_5_bull = "BULLISH" in trend5 or "OVERBOUGHT" in trend5
        is_15_bull = "BULLISH" in trend15 or "OVERBOUGHT" in trend15
        is_5_bear = "BEARISH" in trend5 or "OVERSOLD" in trend5
        is_15_bear = "BEARISH" in trend15 or "OVERSOLD" in trend15
        
        if is_5_bull and is_15_bull:
            conf = "🟢 BULLISH"
            badge_class = "trend-bull"
        elif is_5_bear and is_15_bear:
            conf = "🔴 BEARISH"
            badge_class = "trend-bear"
            
        html += f"""
        <tr>
            <td class="sym-name">{name}</td>
            <td class="price-val" style="font-family: 'JetBrains Mono', monospace;">₹{lp}</td>
            <td class="price-val">
                <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px;">
                    {format_sub_metrics(p5, d.get('5_vwap'), d.get('5_rsi'))}
                    <span class="trend-dot" title="{trend5}" style="width: 10px; height: 10px; border-radius: 50%; display: inline-block; transition: all 0.3s ease; {get_trend_dot_style(trend5)}"></span>
                </div>
            </td>
            <td class="price-val">
                <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px;">
                    {format_sub_metrics(p15, d.get('15_vwap'), d.get('15_rsi'))}
                    <span class="trend-dot" title="{trend15}" style="width: 10px; height: 10px; border-radius: 50%; display: inline-block; transition: all 0.3s ease; {get_trend_dot_style(trend15)}"></span>
                </div>
            </td>
            <td style="text-align: center; vertical-align: middle;">
                <div style="display: flex; align-items: center; justify-content: center; height: 100%;">
                    <span class="trend-dot" title="{conf}" style="width: 14px; height: 14px; border-radius: 50%; display: inline-block; transition: all 0.3s ease; {get_trend_dot_style(conf)}"></span>
                </div>
            </td>
        </tr>
        """
    
    return JSONResponse({"html": html or '<tr><td colspan="5" style="text-align:center; color:#8b949e;">[ NO DATA ]</td></tr>'})

if __name__ == "__main__":
    print("🧹 Cleaning up lingering background engines...")
    subprocess.run("pkill -f fyers_official_logger.py", shell=True)
    subprocess.run("pkill -f fetch_price.py", shell=True)
    
    # Launch uvicorn loop
    uvicorn.run("dashboard_app:app", host="127.0.0.1", port=8080, reload=True)
