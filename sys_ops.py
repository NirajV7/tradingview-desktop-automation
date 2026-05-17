import subprocess
import websocket
import json
import requests
from config import CDP_URL

def is_running(script_name):
    """Accurately checks if a process containing script_name is running via pgrep."""
    try:
        cmd = f"pgrep -f '{script_name}'"
        subprocess.check_output(cmd, shell=True)
        return True
    except:
        return False

def get_tab_info(ws_url):
    """Interrogates a TradingView tab WebSocket for its current Symbol and Timeframe."""
    try:
        ws = websocket.create_connection(ws_url, suppress_origin=True, timeout=2)
        js_code = """
        (() => {
            try {
                const w = (window._exposed_chartWidgetCollection || window.chartWidgetCollection)?.activeChartWidget?.value();
                if (w) {
                    const model = w.model().m_model || w.model();
                    const ms = model.mainSeries ? model.mainSeries() : w.model().mainSeries();
                    return { symbol: ms.symbolInfo().name, interval: String(ms.interval()) };
                }
            } catch(e) {}
            return { symbol: "UNKNOWN", interval: "UNKNOWN" };
        })()
        """
        payload = {"id": 1, "method": "Runtime.evaluate", "params": {"expression": js_code, "returnByValue": True}}
        ws.send(json.dumps(payload))
        res = json.loads(ws.recv())
        ws.close()
        val = res.get("result", {}).get("result", {}).get("value", {})
        if isinstance(val, str): 
            val = json.loads(val)
        sym = val.get("symbol", "UNKNOWN").split(":")[-1].strip().upper()
        return sym, val.get("interval", "UNKNOWN")
    except:
        return "UNKNOWN", "UNKNOWN"
