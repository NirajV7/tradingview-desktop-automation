from fastapi import APIRouter
from fastapi.responses import RedirectResponse, JSONResponse
import subprocess
import os
from datetime import datetime
import requests
import websocket
import random
import time
import json
from urllib.parse import quote_plus

import config
import sys_ops
from dashboard.utils import load_watchlist, make_response

router = APIRouter()

@router.get("/start_tv")
async def start_tv(ajax: bool = False):
    try:
        response = requests.get(config.CDP_URL, timeout=0.5)
        if response.status_code == 200:
            return make_response("TradingView is ALREADY OPEN on Port 9222", "error", ajax)
    except:
        pass # Port is free, proceed with launch

    subprocess.run('open -a "TradingView" --args --remote-debugging-port=9222', shell=True)
    return make_response("TradingView Launch Command Sent", "success", ajax)

@router.get("/stop_tv")
async def stop_tv(ajax: bool = False):
    try:
        subprocess.run("pkill -f TradingView", shell=True)
        return make_response("TradingView Closed Successfully", "success", ajax)
    except Exception as e:
        return make_response(f"Failed to close TradingView: {str(e)}", "error", ajax)

@router.get("/start_fyers")
async def start_fyers(ajax: bool = False):
    if sys_ops.is_running("fyers_official_logger.py"):
        return make_response("Fyers Engine is ALREADY RUNNING", "error", ajax)
    else:
        with open(config.ENGINE_LOG, "a") as log_file:
            subprocess.Popen(
                [config.VENV_PYTHON, "-u", os.path.join(config.CWD, "fyers_official_logger.py")], 
                cwd=config.CWD, 
                stdout=log_file, 
                stderr=log_file
            )
        return make_response("Fyers Engine Started", "success", ajax)

@router.get("/stop_fyers")
async def stop_fyers(ajax: bool = False):
    if not sys_ops.is_running("fyers_official_logger.py"):
        return make_response("Fyers Engine is already Stopped", "error", ajax)
    subprocess.run("pkill -f fyers_official_logger.py", shell=True)
    return make_response("Fyers Engine Stopped Successfully", "success", ajax)

@router.get("/start_kite_engine")
async def start_kite_engine(mode: str = "dry", ajax: bool = False):
    if sys_ops.is_running("kite_execution_engine.py"):
        return make_response("Kite Intraday Engine is ALREADY RUNNING", "error", ajax)
        
    cmd = [config.VENV_PYTHON, "-u", os.path.join(config.CWD, "trade_setup", "kite_execution_engine.py")]
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

@router.get("/stop_kite_engine")
async def stop_kite_engine(ajax: bool = False):
    if not sys_ops.is_running("kite_execution_engine.py"):
        return make_response("Kite Intraday Engine is already Stopped", "error", ajax)
    subprocess.run("pkill -f kite_execution_engine.py", shell=True)
    return make_response("Kite Intraday Engine Stopped Successfully", "success", ajax)

@router.get("/start_tv_log")
async def start_tv_log(ajax: bool = False):
    return make_response("TradingView Scraper is deprecated. Use Fyers Engine.", "error", ajax)

@router.get("/stop_tv_log")
async def stop_tv_log(ajax: bool = False):
    return make_response("TradingView Scraper is deprecated and stopped.", "success", ajax)

@router.get("/clear_logs")
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

@router.get("/sync_tabs")
async def sync_tabs():
    watchlist = load_watchlist()
    symbols_list = watchlist.get("buy", []) + watchlist.get("sell", [])
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

@router.get("/start")
async def start(ajax: bool = False):
    launched = 0
    with open(config.ENGINE_LOG, "a") as log_file:
        log_file.write(f"[{datetime.now().strftime('%H:%M:%S')}] ⚡ START ALL COMMAND RECEIVED...\n")
    
    # 1. Fyers
    if not sys_ops.is_running("fyers_official_logger.py"):
        with open(config.ENGINE_LOG, "a") as log_file:
            subprocess.Popen(
                [config.VENV_PYTHON, "-u", os.path.join(config.CWD, "fyers_official_logger.py")], 
                cwd=config.CWD, 
                stdout=log_file, 
                stderr=log_file
            )
        launched += 1
        
    # 2. Nifty 50 Spike Radar
    if not sys_ops.is_running("nifty_radar.py"):
        with open(config.ENGINE_LOG, "a") as log_file:
            subprocess.Popen(
                [config.VENV_PYTHON, "-u", os.path.join(config.CWD, "nifty_radar.py")], 
                cwd=config.CWD, 
                stdout=log_file, 
                stderr=log_file
            )
        launched += 1
        
    if launched > 0:
        return make_response(f"Successfully Started {launched} Stopped Components", "success", ajax)
    return make_response("All System Engines are already Active", "error", ajax)

@router.get("/start_radar")
async def start_radar(ajax: bool = False):
    launched = 0
    if not sys_ops.is_running("nifty_radar.py"):
        with open(config.ENGINE_LOG, "a") as log_file:
            subprocess.Popen(
                [config.VENV_PYTHON, "-u", os.path.join(config.CWD, "nifty_radar.py")], 
                cwd=config.CWD, 
                stdout=log_file, 
                stderr=log_file
            )
        launched += 1
    if launched > 0:
        return make_response("Nifty 50 Spike Radar Started", "success", ajax)
    return make_response("Nifty 50 Spike Radar is already Active", "error", ajax)

@router.get("/stop")
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

@router.get("/stop_radar")
async def stop_radar(ajax: bool = False):
    stopped = 0
    if sys_ops.is_running("nifty_radar.py"):
        sys_ops.stop_process("nifty_radar.py")
        stopped += 1
    if stopped > 0:
        return make_response("Nifty 50 Spike Radar Stopped", "success", ajax)
    return make_response("Nifty 50 Spike Radar was already Offline", "error", ajax)
