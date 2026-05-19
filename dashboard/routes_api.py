from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import os
import json
import csv
import requests
from datetime import datetime

import config
import sys_ops
import kite_auth_manager
from dashboard.utils import (
    load_watchlist, 
    evaluate_trend_state, 
    get_trend_dot_style, 
    format_sub_metrics
)
from dashboard.cache import fyers_cache

router = APIRouter()

@router.get("/api/search")
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

@router.post("/api/add_symbol")
async def add_symbol(request: Request):
    data = await request.json()
    symbol = data.get('symbol')
    direction = data.get('direction', 'buy').lower()
    if direction not in ['buy', 'sell']:
        direction = 'buy'
    
    watchlist = load_watchlist()
    
    if symbol:
        # Move from other list if it is there
        other_dir = 'sell' if direction == 'buy' else 'buy'
        if symbol in watchlist.get(other_dir, []):
            watchlist[other_dir].remove(symbol)
            
        if symbol not in watchlist.get(direction, []):
            watchlist[direction].append(symbol)
            
        with open(config.WATCHLIST_FILE, "w") as f:
            json.dump(watchlist, f)
            
    return JSONResponse({"status": "ok"})

@router.post("/api/remove_symbol")
async def remove_symbol(request: Request):
    data = await request.json()
    symbol = data.get('symbol')
    
    watchlist = load_watchlist()
    
    modified = False
    for direction in ['buy', 'sell']:
        if symbol in watchlist.get(direction, []):
            watchlist[direction].remove(symbol)
            modified = True
            
    if modified:
        with open(config.WATCHLIST_FILE, "w") as f:
            json.dump(watchlist, f)
            
    return JSONResponse({"status": "ok"})

@router.get("/api/status")
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

@router.get("/api/logs")
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

@router.get("/api/data")
async def api_data():
    watchlist = load_watchlist()
    buy_symbols = watchlist.get("buy", [])
    sell_symbols = watchlist.get("sell", [])
    active_symbols = buy_symbols + sell_symbols
    
    active_names = [s.split(":")[1].split("-")[0] if ":" in s else s for s in active_symbols]
    data_map = {}

    # Initialize data map for each active symbol
    for sym in active_symbols:
        name = sym.split(":")[1].split("-")[0] if ":" in sym else sym
        data_map[name] = {
            'symbol': name,
            'full_symbol': sym,
            'direction': 'BUY' if sym in buy_symbols else 'SELL',
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
            from collections import deque
            with open(config.FYERS_LOG, "r") as f:
                header_line = f.readline().strip()
                if header_line:
                    header = header_line.split(',')
                    last_lines = deque(f, maxlen=300)
                    reader = csv.DictReader(last_lines, fieldnames=header)
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

    # Render HTML Rows
    html = ""
    for name in active_names:
        d = data_map.get(name, {})
        lp = d.get('lp', '...')
        direction = d.get('direction', 'BUY')
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
            
        if direction == 'BUY':
            dir_badge = '<span style="background: rgba(63, 185, 80, 0.12); color: #3fb950; font-size: 0.72em; padding: 2px 6px; border-radius: 4px; font-weight: bold; margin-left: 8px; border: 1px solid rgba(63, 185, 80, 0.25);">BUY</span>'
        else:
            dir_badge = '<span style="background: rgba(248, 81, 73, 0.12); color: #f85149; font-size: 0.72em; padding: 2px 6px; border-radius: 4px; font-weight: bold; margin-left: 8px; border: 1px solid rgba(248, 81, 73, 0.25);">SELL</span>'

        html += f"""
        <tr>
            <td class="sym-name">{name}{dir_badge}</td>
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
