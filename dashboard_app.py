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
import asyncio
from threading import Lock
import subprocess
from datetime import datetime, timedelta
import uvicorn
from urllib.parse import quote_plus

import config
import auth_manager
import kite_auth_manager
import sys_ops
from fyers_apiv3 import fyersModel
from indicator_engine import compute_indicators, calculate_adr_percentage, calculate_adr_absolute

app = FastAPI(title="NJ Quant Terminal")

class FyersHistoryCache:
    def __init__(self):
        self.lock = Lock()
        self.data_5m = {}  # symbol -> list of indicator dicts
        self.data_15m = {} # symbol -> list of indicator dicts
        self.last_update = None

    def update(self, data_5m, data_15m):
        with self.lock:
            self.data_5m = data_5m
            self.data_15m = data_15m
            self.last_update = datetime.now()

    def get_indicators(self, symbol):
        with self.lock:
            return self.data_5m.get(symbol, []), self.data_15m.get(symbol, [])

fyers_cache = FyersHistoryCache()

def log_fyers_indicators_to_csv(file_path, symbol, candle):
    """Appends computed indicator values to the specified CSV file if not already logged for this timestamp.
    Returns True if successfully written, False if skipped as duplicate.
    """
    try:
        file_exists = os.path.exists(file_path)
        if file_exists:
            try:
                with open(file_path, "r") as f:
                    f.seek(0, 2)
                    size = f.tell()
                    # Read the last 8KB of the file to scan for duplicates across all active watchlist symbols
                    f.seek(max(0, size - 8192))
                    tail = f.read()
                    if f"{candle['timestamp']},{symbol}" in tail:
                        return False  # Already logged this timestamp for this stock
            except Exception as e:
                pass
                
        with open(file_path, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["timestamp", "symbol", "price", "ema20", "ema50", "ema200", "rsi", "vwap", "volume", "adr", "adr_abs"])
            
            p = candle.get("close", 0.0)
            e20 = candle.get("ema20")
            e50 = candle.get("ema50")
            e200 = candle.get("ema200")
            rsi = candle.get("rsi")
            v = candle.get("vwap")
            vol = candle.get("volume", 0)
            adr = candle.get("adr")
            adr_abs = candle.get("adr_abs")
            
            e20_val = f"{e20:.2f}" if e20 is not None else ""
            e50_val = f"{e50:.2f}" if e50 is not None else ""
            e200_val = f"{e200:.2f}" if e200 is not None else ""
            rsi_val = f"{rsi:.2f}" if rsi is not None else ""
            v_val = f"{v:.2f}" if v is not None else ""
            adr_val = f"{adr:.2f}" if adr is not None else ""
            adr_abs_val = f"{adr_abs:.2f}" if adr_abs is not None else ""
            
            writer.writerow([
                candle["timestamp"],
                symbol,
                f"{p:.2f}",
                e20_val,
                e50_val,
                e200_val,
                rsi_val,
                v_val,
                vol,
                adr_val,
                adr_abs_val
            ])
        return True
    except Exception as e:
        print(f"[CSV LOG ERROR] Failed to append indicators for {symbol} to {file_path}: {e}")
        return False

def get_last_closed_candle(indicators, timeframe_minutes):
    """Returns the latest candle in the array that is fully closed (finalized)."""
    if not indicators:
        return None
    
    last_candle = indicators[-1]
    try:
        dt = datetime.strptime(last_candle["timestamp"], "%Y-%m-%d %H:%M:%S")
        # Add 5-second grace window to protect against minor clock variances
        end_dt = dt + timedelta(minutes=timeframe_minutes) - timedelta(seconds=5)
        if datetime.now() >= end_dt:
            return last_candle
    except Exception as e:
        pass
        
    if len(indicators) > 1:
        return indicators[-2]
    return last_candle

async def fyers_cache_updater():
    """Background task to refresh Fyers history indicators every 60 seconds."""
    while True:
        try:
            active_symbols = load_watchlist()
            if not active_symbols:
                await asyncio.sleep(5)
                continue

            # Load Fyers model
            token_file = config.TOKEN_FILE
            if not os.path.exists(token_file):
                await asyncio.sleep(10)
                continue

            try:
                with open(token_file, "r") as f:
                    token_data = json.load(f)
                    access_token = token_data.get("access_token")
            except Exception as e:
                print(f"[CACHE ERROR] Failed reading token file: {e}")
                await asyncio.sleep(10)
                continue

            if not access_token:
                await asyncio.sleep(10)
                continue

            fyers = fyersModel.FyersModel(
                client_id=config.CLIENT_ID,
                is_async=False,
                token=access_token,
                log_path=os.getcwd()
            )

            new_5m = {}
            new_15m = {}

            today_str = datetime.now().strftime("%Y-%m-%d")
            from_5d_str = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
            from_15d_str = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d")
            from_30d_str = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

            for symbol in active_symbols:
                # 0. Fetch Daily History and compute ADR (last 30 days is safe to cover 14 trading days)
                adr_val = None
                adr_abs_val = None
                try:
                    res_d = fyers.history({
                        "symbol": symbol,
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
                    print(f"[CACHE ERROR] Failed daily ADR for {symbol}: {e}")

                # 5m History (needs ~2.6 days for 200 EMA, 5 days is safe)
                try:
                    res = fyers.history({
                        "symbol": symbol,
                        "resolution": "5",
                        "date_format": "1",
                        "range_from": from_5d_str,
                        "range_to": today_str,
                        "cont_flag": "1"
                    })
                    if res.get("s") == "ok":
                        candles = res.get("candles", [])
                        if candles:
                            indicators = compute_indicators(candles)
                            # Inject ADR values into the indicator objects
                            for item in indicators:
                                item["adr"] = adr_val
                                item["adr_abs"] = adr_abs_val
                            new_5m[symbol] = indicators
                            closed_candle = get_last_closed_candle(indicators, 5)
                            if closed_candle:
                                log_fyers_indicators_to_csv(config.FYERS_INDICATORS_5M, symbol, closed_candle)
                except Exception as e:
                    print(f"[CACHE ERROR] Failed 5m for {symbol}: {e}")

                # 15m History (needs ~8 days for 200 EMA, 15 days is safe)
                try:
                    res = fyers.history({
                        "symbol": symbol,
                        "resolution": "15",
                        "date_format": "1",
                        "range_from": from_15d_str,
                        "range_to": today_str,
                        "cont_flag": "1"
                    })
                    if res.get("s") == "ok":
                        candles = res.get("candles", [])
                        if candles:
                            indicators = compute_indicators(candles)
                            # Inject ADR values into the indicator objects
                            for item in indicators:
                                item["adr"] = adr_val
                                item["adr_abs"] = adr_abs_val
                            new_15m[symbol] = indicators
                            closed_candle = get_last_closed_candle(indicators, 15)
                            if closed_candle:
                                log_fyers_indicators_to_csv(config.FYERS_INDICATORS_15M, symbol, closed_candle)
                except Exception as e:
                    print(f"[CACHE ERROR] Failed 15m for {symbol}: {e}")

                # Sleep slightly to respect rate limits
                await asyncio.sleep(0.1)

            # Update cache
            fyers_cache.update(new_5m, new_15m)
            print(f"[CACHE SUCCESS] Refreshed indicators for {len(active_symbols)} symbols at {datetime.now().strftime('%H:%M:%S')}")

        except Exception as e:
            print(f"[CACHE ERROR] General exception in updater loop: {e}")

        await asyncio.sleep(60)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(fyers_cache_updater())


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
    kite_needs_login, kite_auth_url = kite_auth_manager.check_kite_auth()
    symbols_list = load_watchlist()
    
    current_symbols_text = ", ".join([s.split(":")[1].split("-")[0] if ":" in s else s for s in symbols_list])
    
    kite_margin = None
    if not kite_needs_login:
        kite_margin = kite_auth_manager.get_kite_margin()
        
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request, 
            "needs_login": needs_login, 
            "auth_url": auth_url,
            "kite_needs_login": kite_needs_login,
            "kite_auth_url": kite_auth_url,
            "kite_margin": kite_margin,
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

@app.get("/kite_auth")
async def kite_auth(request_token: str = None):
    if not request_token:
        return RedirectResponse(url="/?msg=No+request+token+received&msg_type=error", status_code=303)
    success, message = kite_auth_manager.exchange_kite_token(request_token.strip())
    if success:
        return RedirectResponse(url="/?msg=Kite+Authorized+Successfully&msg_type=success", status_code=303)
    else:
        return RedirectResponse(url=f"/?msg={quote_plus(message)}&msg_type=error", status_code=303)

@app.post("/kite_auth")
async def kite_auth_post(request_token_input: str = Form(...)):
    token = request_token_input.strip()
    if "request_token=" in token:
        try:
            token = token.split("request_token=")[1].split("&")[0]
        except Exception:
            pass
            
    success, message = kite_auth_manager.exchange_kite_token(token)
    if success:
        return RedirectResponse(url="/?msg=Kite+Authorized+Successfully&msg_type=success", status_code=303)
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

@app.get("/start_kite_engine")
async def start_kite_engine(mode: str = "dry", ajax: bool = False):
    if sys_ops.is_running("kite_execution_engine.py"):
        return make_response("Kite Intraday Engine is ALREADY RUNNING", "error", ajax)
        
    cmd = [config.VENV_PYTHON, os.path.join(config.CWD, "trade_setup", "kite_execution_engine.py")]
    if mode == "live":
        cmd.append("live")
        
    with open(config.ENGINE_LOG, "a") as log_file:
        subprocess.Popen(
            cmd,
            cwd=config.CWD,
            stdout=log_file,
            stderr=log_file
        )
    mode_str = "LIVE" if mode == "live" else "DRY RUN (Simulated)"
    return make_response(f"Kite Intraday Engine Started in {mode_str} Mode", "success", ajax)

@app.get("/stop_kite_engine")
async def stop_kite_engine(ajax: bool = False):
    if not sys_ops.is_running("kite_execution_engine.py"):
        return make_response("Kite Intraday Engine is already Stopped", "error", ajax)
    subprocess.run("pkill -f kite_execution_engine.py", shell=True)
    return make_response("Kite Intraday Engine Stopped Successfully", "success", ajax)

@app.get("/start_tv_log")
async def start_tv_log(ajax: bool = False):
    return make_response("TradingView Scraper is deprecated. Use Fyers Engine.", "error", ajax)

@app.get("/stop_tv_log")
async def stop_tv_log(ajax: bool = False):
    return make_response("TradingView Scraper is deprecated and stopped.", "success", ajax)

@app.get("/clear_logs")
async def clear_logs():
    targets = [
        config.TRADING_LOG,
        config.TRADING_LOG_5M,
        config.TRADING_LOG_15M,
        config.FYERS_LOG,
        config.FYERS_LOG_5M,
        config.FYERS_LOG_15M,
        config.FYERS_INDICATORS_5M,
        config.FYERS_INDICATORS_15M,
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

@app.get("/start")
async def start(ajax: bool = False):
    launched = 0
    with open(config.ENGINE_LOG, "a") as log_file:
        log_file.write(f"[{datetime.now().strftime('%H:%M:%S')}] ⚡ START ALL COMMAND RECEIVED...\n")
    
    # 1. Fyers
    if not sys_ops.is_running("fyers_official_logger.py"):
        with open(config.ENGINE_LOG, "a") as log_file:
            subprocess.Popen(
                [config.VENV_PYTHON, os.path.join(config.CWD, "fyers_official_logger.py")], 
                cwd=config.CWD, 
                stdout=log_file, 
                stderr=log_file
            )
        launched += 1
        
    # 2. Nifty 50 Spike Radar
    if not sys_ops.is_running("nifty_radar.py"):
        with open(config.ENGINE_LOG, "a") as log_file:
            subprocess.Popen(
                [config.VENV_PYTHON, os.path.join(config.CWD, "nifty_radar.py")], 
                cwd=config.CWD, 
                stdout=log_file, 
                stderr=log_file
            )
        launched += 1
        
    if launched > 0:
        return make_response(f"Successfully Started {launched} Stopped Components", "success", ajax)
    return make_response("All System Engines are already Active", "error", ajax)

@app.get("/start_radar")
async def start_radar(ajax: bool = False):
    launched = 0
    if not sys_ops.is_running("nifty_radar.py"):
        with open(config.ENGINE_LOG, "a") as log_file:
            subprocess.Popen(
                [config.VENV_PYTHON, os.path.join(config.CWD, "nifty_radar.py")], 
                cwd=config.CWD, 
                stdout=log_file, 
                stderr=log_file
            )
        launched += 1
    if launched > 0:
        return make_response("Nifty 50 Spike Radar Started", "success", ajax)
    return make_response("Nifty 50 Spike Radar is already Active", "error", ajax)

@app.get("/stop")
async def stop(ajax: bool = False):
    stopped = 0
    with open(config.ENGINE_LOG, "a") as log_file:
        log_file.write(f"[{datetime.now().strftime('%H:%M:%S')}] 🛑 STOP ALL COMMAND RECEIVED...\n")
        
    if sys_ops.is_running("fyers_official_logger.py"):
        subprocess.run("pkill -f fyers_official_logger.py", shell=True)
        stopped += 1
    if sys_ops.is_running("nifty_radar.py"):
        sys_ops.stop_process("nifty_radar.py")
        stopped += 1
    if sys_ops.is_running("kite_execution_engine.py"):
        subprocess.run("pkill -f kite_execution_engine.py", shell=True)
        stopped += 1
        

    with open(config.ENGINE_LOG, "a") as log_file:
        log_file.write(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ System shutdown complete. {stopped} engines killed.\n")

    if stopped > 0:
        return make_response(f"Successfully Stopped {stopped} Components", "success", ajax)
    return make_response("All Components were already Stopped", "error", ajax)

@app.get("/stop_radar")
async def stop_radar(ajax: bool = False):
    stopped = 0
    if sys_ops.is_running("nifty_radar.py"):
        sys_ops.stop_process("nifty_radar.py")
        stopped += 1
    if stopped > 0:
        return make_response("Nifty 50 Spike Radar Stopped", "success", ajax)
    return make_response("Nifty 50 Spike Radar was already Offline", "error", ajax)

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
        
    kite_needs_login, _ = kite_auth_manager.check_kite_auth()
    kite_margin = None
    if not kite_needs_login:
        kite_margin = kite_auth_manager.get_kite_margin()
        
    kite_engine_state = "stopped"
    if sys_ops.is_running("kite_execution_engine.py live"):
        kite_engine_state = "live"
    elif sys_ops.is_running("kite_execution_engine.py"):
        kite_engine_state = "dry"
        
    return JSONResponse({
        "tv": tv_open,
        "fyers": sys_ops.is_running("fyers_official_logger.py"),
        "log": False,
        "radar": sys_ops.is_running("nifty_radar.py"),
        "kite_engine": kite_engine_state,
        "kite_margin": kite_margin
    })

@app.get("/api/kite/orders")
async def api_kite_orders():
    orders = kite_auth_manager.get_kite_orders()
    return JSONResponse({"orders": orders})

@app.get("/api/kite/positions")
async def api_kite_positions():
    positions = kite_auth_manager.get_kite_positions()
    orders = kite_auth_manager.get_kite_orders()
    
    enriched_positions = []
    for p in positions:
        symbol = p.get("symbol")
        qty = p.get("quantity", 0)
        avg_price = p.get("average_price", 0.0)
        last_price = p.get("last_price", 0.0)
        
        # 1. Match active orders for target and SL
        target_price = None
        target_order_id = None
        sl_price = None
        sl_order_id = None
        
        # In MIS:
        # If long (qty > 0): target is a pending SELL LIMIT order, SL is a pending SELL SL/SL-M order
        # If short (qty < 0): target is a pending BUY LIMIT order, SL is a pending BUY SL/SL-M order
        expected_tx = "SELL" if qty > 0 else "BUY"
        
        for o in orders:
            if o.get("symbol") == symbol and o.get("status") in ["OPEN", "TRIGGER PENDING"]:
                if o.get("transaction_type") == expected_tx:
                    otype = o.get("order_type")
                    if otype == "LIMIT":
                        target_price = o.get("price")
                        target_order_id = o.get("order_id")
                    elif otype in ["SL", "SL-M"]:
                        sl_price = o.get("trigger_price") or o.get("price")
                        sl_order_id = o.get("order_id")
        
        # 2. Get ADR values from Fyers cache
        fyers_sym = None
        for s in fyers_cache.data_5m.keys():
            if symbol in s:
                fyers_sym = s
                break
        
        adr_val = None
        adr_abs_val = None
        if fyers_sym:
            ind_5m = fyers_cache.data_5m.get(fyers_sym, [])
            if ind_5m:
                last_ind = ind_5m[-1]
                adr_val = last_ind.get("adr")
                adr_abs_val = last_ind.get("adr_abs")
        
        # 3. Calculate Risk Allocated & Risk %
        allocated_risk = 0.0
        risk_pct = 0.0
        
        if qty != 0:
            effective_sl = sl_price
            if not effective_sl and adr_abs_val:
                effective_sl = avg_price - adr_abs_val if qty > 0 else avg_price + adr_abs_val
            
            if effective_sl:
                allocated_risk = abs(qty * (avg_price - effective_sl))
                # Base on maximum ₹2,500 absolute risk limit
                risk_pct = min(100.0, (allocated_risk / 2500.0) * 100.0)
        
        ghost_oco_active = (target_order_id is not None) and (sl_order_id is not None)
        
        enriched_positions.append({
            "symbol": symbol,
            "quantity": qty,
            "average_price": avg_price,
            "last_price": last_price,
            "pnl": p.get("pnl", 0.0),
            "product": p.get("product"),
            "target_price": target_price,
            "target_order_id": target_order_id,
            "sl_price": sl_price,
            "sl_order_id": sl_order_id,
            "ghost_oco_active": ghost_oco_active,
            "adr": adr_val,
            "adr_abs": adr_abs_val,
            "allocated_risk": round(allocated_risk, 2),
            "risk_pct": round(risk_pct, 1)
        })
        
    return JSONResponse({"positions": enriched_positions})

@app.post("/api/kite/panic")
async def api_kite_panic():
    res = kite_auth_manager.panic_square_off()
    if res.get("status") == "error":
        return JSONResponse(res, status_code=500)
    elif res.get("status") == "partial":
        return JSONResponse(res, status_code=207)
    return JSONResponse(res)

@app.post("/api/kite/exit_position")
async def api_kite_exit_position(payload: dict):
    symbol = payload.get("symbol")
    if not symbol:
        return JSONResponse({"status": "error", "message": "Symbol is required"}, status_code=400)
    res = kite_auth_manager.exit_single_position(symbol)
    if res.get("status") == "error":
        return JSONResponse(res, status_code=500)
    return JSONResponse(res)



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

    # Initialize data map for each active symbol
    for sym in active_symbols:
        name = sym.split(":")[1].split("-")[0] if ":" in sym else sym
        data_map[name] = {
            'symbol': name,
            'full_symbol': sym,
            'lp': '...',
            '5_close': '...',
            '5_vwap': '...',
            '5_ema20': '...',
            '5_ema50': '...',
            '5_ema200': '...',
            '5_rsi': '...',
            '15_close': '...',
            '15_vwap': '...',
            '15_ema20': '...',
            '15_ema50': '...',
            '15_ema200': '...',
            '15_rsi': '...'
        }

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
                        if name in data_map:
                            data_map[name]['lp'] = row.get('last_price', '...')
        except: 
            pass

    # 2. Inject cached Fyers indicators
    for sym in active_symbols:
        name = sym.split(":")[1].split("-")[0] if ":" in sym else sym
        ind_5m, ind_15m = fyers_cache.get_indicators(sym)
        
        if ind_5m:
            last_5 = ind_5m[-1]
            data_map[name]['5_close'] = last_5['close']
            data_map[name]['5_vwap'] = f"{last_5['vwap']:.2f}"
            data_map[name]['5_ema20'] = f"{last_5['ema20']:.2f}"
            data_map[name]['5_ema50'] = f"{last_5['ema50']:.2f}"
            data_map[name]['5_ema200'] = f"{last_5['ema200']:.2f}"
            data_map[name]['5_rsi'] = f"{last_5['rsi']:.2f}"
            
        if ind_15m:
            last_15 = ind_15m[-1]
            data_map[name]['15_close'] = last_15['close']
            data_map[name]['15_vwap'] = f"{last_15['vwap']:.2f}"
            data_map[name]['15_ema20'] = f"{last_15['ema20']:.2f}"
            data_map[name]['15_ema50'] = f"{last_15['ema50']:.2f}"
            data_map[name]['15_ema200'] = f"{last_15['ema200']:.2f}"
            data_map[name]['15_rsi'] = f"{last_15['rsi']:.2f}"

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
        lp = d.get('lp', '...')
        p5 = lp if lp != '...' else d.get('5_close', '...')
        p15 = lp if lp != '...' else d.get('15_close', '...')
        
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

# -------------------------------------------------------------
# NIFTY 50 SPIKE RADAR API CHANNELS
# -------------------------------------------------------------

RADAR_ALERTS = []  # Ring buffer of alerts: max length 20

@app.post("/api/radar/alert")
async def api_radar_alert(request: Request):
    try:
        data = await request.json()
        symbol = data.get("symbol")
        ltp = data.get("ltp")
        volume_ratio = data.get("volume_ratio")
        price_change = data.get("price_change")
        
        alert_item = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "symbol": symbol,
            "ltp": ltp,
            "volume_ratio": volume_ratio,
            "price_change": price_change
        }
        
        # Insert at the beginning of list
        RADAR_ALERTS.insert(0, alert_item)
        if len(RADAR_ALERTS) > 20:
            RADAR_ALERTS.pop()
            
        return JSONResponse({"status": "ok"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/api/radar/alerts")
async def api_radar_alerts():
    return JSONResponse(RADAR_ALERTS)

@app.post("/api/radar/clear")
@app.get("/api/radar/clear")
async def api_radar_clear():
    RADAR_ALERTS.clear()
    return JSONResponse({"status": "ok", "message": "Momentum Radar alert store cleared"})

@app.post("/api/radar/switch")
async def api_radar_switch(request: Request):
    try:
        data = await request.json()
        symbol = data.get("symbol") # E.g., "RELIANCE"
        if not symbol:
            return JSONResponse({"status": "error", "message": "Symbol is required"}, status_code=400)
            
        # Communicate via CDP to target TradingView active tabs
        response = requests.get(config.CDP_URL, timeout=1.0)
        tabs = [t for t in response.json() if "tradingview.com/chart" in t.get("url", "")]
        if not tabs:
            return JSONResponse({"status": "error", "message": "No active TradingView tabs found"}, status_code=404)
            
        # Switch tab context to matching symbol
        target_tab = None
        for t in tabs:
            sym, _ = sys_ops.get_tab_info(t.get("webSocketDebuggerUrl"))
            if sym.upper() == symbol.upper():
                target_tab = t
                break
                
        if target_tab:
            # We found a tab that already has the symbol! Bring it to front!
            ws_url = target_tab.get("webSocketDebuggerUrl")
            ws = websocket.create_connection(ws_url, suppress_origin=True, timeout=2)
            payload = {"id": random.randint(1, 10000), "method": "Page.bringToFront"}
            ws.send(json.dumps(payload))
            ws.close()
            return JSONResponse({"status": "ok", "action": "brought_to_front"})
        else:
            # Not open, let's navigate the *first* tab to this symbol!
            target_tab = tabs[0]
            ws_url = target_tab.get("webSocketDebuggerUrl")
            ws = websocket.create_connection(ws_url, suppress_origin=True, timeout=2)
            
            target_url = f"https://in.tradingview.com/chart/?symbol=NSE:{symbol}"
            js_code = f"window.location.href = '{target_url}';"
            payload = {
                "id": random.randint(1, 10000),
                "method": "Runtime.evaluate",
                "params": {"expression": js_code}
            }
            ws.send(json.dumps(payload))
            # Also bring this tab to front!
            ws.send(json.dumps({"id": random.randint(1, 10000), "method": "Page.bringToFront"}))
            ws.close()
            return JSONResponse({"status": "ok", "action": "navigated_tab"})
            
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

if __name__ == "__main__":
    print("🧹 Cleaning up lingering background engines...")
    subprocess.run("pkill -f fyers_official_logger.py", shell=True)
    subprocess.run("pkill -f fetch_price.py", shell=True)
    sys_ops.stop_process("nifty_radar.py")
    subprocess.run("pkill -f kite_execution_engine.py", shell=True)
    
    # Launch uvicorn loop
    uvicorn.run("dashboard_app:app", host="127.0.0.1", port=8080, reload=True)
