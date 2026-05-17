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

@app.get("/start_tv")
async def start_tv():
    try:
        response = requests.get(config.CDP_URL, timeout=0.5)
        if response.status_code == 200:
            return RedirectResponse(url="/?msg=TradingView+is+ALREADY+OPEN+on+Port+9222&msg_type=error", status_code=303)
    except:
        pass # Port is free, proceed with launch

    subprocess.run('open -a "TradingView" --args --remote-debugging-port=9222', shell=True)
    return RedirectResponse(url="/?msg=TradingView+Launch+Command+Sent&msg_type=success", status_code=303)

@app.get("/start_fyers")
async def start_fyers():
    if sys_ops.is_running("fyers_official_logger.py"):
        return RedirectResponse(url="/?msg=Fyers+Engine+is+ALREADY+RUNNING&msg_type=error", status_code=303)
    else:
        with open(config.ENGINE_LOG, "a") as log_file:
            subprocess.Popen(
                [config.VENV_PYTHON, os.path.join(config.CWD, "fyers_official_logger.py")], 
                cwd=config.CWD, 
                stdout=log_file, 
                stderr=log_file
            )
        return RedirectResponse(url="/?msg=Fyers+Engine+Started&msg_type=success", status_code=303)

@app.get("/start_tv_log")
async def start_tv_log():
    if sys_ops.is_running("fetch_price.py"):
        return RedirectResponse(url="/?msg=TV+Scraper+is+ALREADY+RUNNING&msg_type=error", status_code=303)
    else:
        with open(config.ENGINE_LOG, "a") as log_file:
            subprocess.Popen(
                [config.VENV_PYTHON, os.path.join(config.CWD, "fetch_price.py")], 
                cwd=config.CWD, 
                stdout=log_file, 
                stderr=log_file
            )
        return RedirectResponse(url="/?msg=TradingView+Price+Scraper+Started&msg_type=success", status_code=303)

@app.get("/clear_logs")
async def clear_logs():
    for f in [config.TRADING_LOG, config.FYERS_LOG, config.ENGINE_LOG]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except:
                pass
    return RedirectResponse(url="/?msg=All+Logs+Wiped!&msg_type=success", status_code=303)

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

@app.get("/stop")
async def stop():
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
        return RedirectResponse(url=f"/?msg=Successfully+Stopped+{stopped}+Engines&msg_type=success", status_code=303)
    else:
        return RedirectResponse(url="/?msg=All+Engines+were+already+Stopped&msg_type=error", status_code=303)

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
                        
                        for key, val in row.items():
                            if "Volume Weighted Average Price" in key or "VWAP" in key:
                                if val: 
                                    data_map[name][f"{tf}_vwap"] = val
        except: 
            pass

    # Render HTML Rows
    html = ""
    for name in active_names:
        d = data_map.get(name, {})
        p5 = d.get('5', '...')
        p15 = d.get('15', '...')
        lp = d.get('lp', '...')
        
        conf = "WAITING"
        badge_class = "trend-neut"
        
        try:
            if p5 != '...' and p15 != '...':
                vwap5 = d.get('5_vwap')
                vwap15 = d.get('15_vwap')
                
                is_5_up = float(p5) > float(vwap5) if vwap5 else True
                is_15_up = float(p15) > float(vwap15) if vwap15 else True
                
                if is_5_up and is_15_up:
                    conf = "BULLISH"
                    badge_class = "trend-bull"
                elif not is_5_up and not is_15_up:
                    conf = "BEARISH"
                    badge_class = "trend-bear"
                else:
                    conf = "CONFLICT"
                    badge_class = "trend-neut"
        except:
            conf = "ERROR"
            
        html += f"""
        <tr>
            <td class="sym-name">{name}</td>
            <td class="price-val">₹{lp}</td>
            <td class="price-val">{p5}</td>
            <td class="price-val">{p15}</td>
            <td><span class="trend-badge {badge_class}">{conf}</span></td>
        </tr>
        """
    
    return JSONResponse({"html": html or '<tr><td colspan="5" style="text-align:center; color:#8b949e;">[ NO DATA ]</td></tr>'})

if __name__ == "__main__":
    print("🧹 Cleaning up lingering background engines...")
    subprocess.run("pkill -f fyers_official_logger.py", shell=True)
    subprocess.run("pkill -f fetch_price.py", shell=True)
    
    # Launch uvicorn loop
    uvicorn.run("fastapi_app:app", host="127.0.0.1", port=8080, reload=True)
