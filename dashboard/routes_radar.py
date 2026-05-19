from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from datetime import datetime
import requests
import websocket
import random
import json

import config
import sys_ops
from dashboard.cache import RADAR_ALERTS

router = APIRouter()

@router.post("/api/radar/alert")
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

@router.get("/api/radar/alerts")
async def api_radar_alerts():
    return JSONResponse(RADAR_ALERTS)

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
