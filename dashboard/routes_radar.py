from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from datetime import datetime
import requests
import websocket
import random
import json
import os

import config
import sys_ops
import kite_auth_manager
from dashboard.cache import RADAR_ALERTS

router = APIRouter()

def load_radar_watchlist():
    path = config.RADAR_WATCHLIST_FILE
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_radar_watchlist(watchlist):
    path = config.RADAR_WATCHLIST_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(watchlist, f, indent=4)

@router.post("/api/radar/alert")
def api_radar_alert(data: dict):
    try:
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
            
        # Update radar watchlist file
        if symbol:
            base_symbol = symbol.replace("NSE:", "").replace("-EQ", "").upper()
            full_symbol = f"NSE:{base_symbol}-EQ"
            
            # Check main watchlist.json
            main_watchlist = {}
            if os.path.exists(config.WATCHLIST_FILE):
                try:
                    with open(config.WATCHLIST_FILE, "r") as f:
                        main_watchlist = json.load(f)
                except Exception:
                    pass
            
            buy_list = [s.replace("NSE:", "").replace("-EQ", "").upper() for s in main_watchlist.get("buy", [])]
            sell_list = [s.replace("NSE:", "").replace("-EQ", "").upper() for s in main_watchlist.get("sell", [])]
            
            if base_symbol not in buy_list and base_symbol not in sell_list:
                # Check active positions
                active_symbols = []
                try:
                    positions = kite_auth_manager.get_kite_positions()
                    active_symbols = [p.get("symbol", "").upper() for p in positions if p.get("quantity", 0) != 0]
                except Exception as e:
                    print(f"⚠️ Failed to get positions for radar check: {e}")
                
                if base_symbol not in active_symbols:
                    watchlist = load_radar_watchlist()
                    # Check if already in radar watchlist
                    if not any(item.get("symbol") == full_symbol for item in watchlist):
                        spike_open = round(ltp / (1 + (price_change / 100.0)), 2)
                        new_item = {
                            "symbol": full_symbol,
                            "direction": "BUY" if price_change > 0 else "SELL",
                            "spike_price": ltp,
                            "spike_open": spike_open,
                            "spike_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "state": "WAITING_FOR_PULLBACK",
                            "pullback_low": None,
                            "pullback_high": None
                        }
                        watchlist.append(new_item)
                        save_radar_watchlist(watchlist)
                        print(f"📡 Added {full_symbol} to Radar Watchlist: {new_item['direction']} pullback scan.")
            
        return JSONResponse({"status": "ok"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@router.get("/api/radar/alerts")
async def api_radar_alerts():
    return JSONResponse(RADAR_ALERTS)

@router.get("/api/radar/watchlist")
async def api_get_radar_watchlist():
    return JSONResponse(load_radar_watchlist())

@router.post("/api/radar/watchlist/remove")
async def api_remove_radar_watchlist(request: Request):
    try:
        data = await request.json()
        symbol = data.get("symbol")
        if not symbol:
            return JSONResponse({"status": "error", "message": "Symbol is required"}, status_code=400)
        
        base_symbol = symbol.replace("NSE:", "").replace("-EQ", "").upper()
        full_symbol = f"NSE:{base_symbol}-EQ"
        
        watchlist = load_radar_watchlist()
        filtered = [item for item in watchlist if item.get("symbol") != full_symbol]
        save_radar_watchlist(filtered)
        return JSONResponse({"status": "ok", "message": f"Removed {full_symbol} from Radar watchlist"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@router.post("/api/radar/clear")
@router.get("/api/radar/clear")
async def api_radar_clear():
    RADAR_ALERTS.clear()
    return JSONResponse({"status": "ok", "message": "Momentum Radar alert store cleared"})

@router.post("/api/radar/switch")
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
