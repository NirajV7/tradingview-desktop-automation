import requests
import websocket
import json
import time
import random
import csv
import os
from datetime import datetime

def fetch_all_tv_prices():
    try:
        response = requests.get("http://localhost:9222/json")
        tabs = [t for t in response.json() if "tradingview.com/chart" in t.get("url", "")]
    except Exception as e:
        return f"Error: {e}"

    if not tabs: return "Error: No chart tabs found"

    results = []
    
    # JS logic to get everything: Price, Timeframe, and ALL Indicators
    js_code = """
    (() => {
        let res = { symbol: "Unknown", price: "Unknown", timeframe: "Unknown", indicators: {} };
        const round = (val) => (typeof val === 'number') ? Math.round(val * 100) / 100 : val;
        try {
            const w = (window._exposed_chartWidgetCollection || window.chartWidgetCollection)?.activeChartWidget?.value();
            if (w) {
                const modelWrapper = w.model();
                const model = modelWrapper.m_model || modelWrapper;
                const ms = model.mainSeries ? model.mainSeries() : modelWrapper.mainSeries();
                res.symbol = ms.symbolInfo().name;
                res.timeframe = ms.interval(); // Fetch timeframe
                
                // 1. Get Price
                const data = ms.data();
                if (data.m_bars && data.m_bars._items) {
                    const items = data.m_bars._items;
                    if (items.length > 0) {
                        const lastBar = items[items.length - 1];
                        res.price = round(lastBar.value[4] || lastBar.value[1]);
                    }
                }
                
                // 2. Get ALL Indicators
                const studies = model.allStudies ? model.allStudies() : [];
                for (let s of studies) {
                    const desc = s.metaInfo().description;
                    const sData = s.data();
                    const items = sData._items || (sData.m_bars ? sData.m_bars._items : null);
                    
                    if (items && items.length > 0) {
                        let val = items[items.length - 1].value[1]; 
                        if (val !== undefined) {
                            val = round(val);
                            let name = desc;
                            let i = 1;
                            while (res.indicators[name]) { name = desc + " " + (++i); }
                            res.indicators[name] = val;
                        }
                    }
                }
            }
        } catch(e) { res.error = e.message; }
        return JSON.stringify(res);
    })()
    """

    for tab in tabs:
        try:
            ws = websocket.create_connection(tab["webSocketDebuggerUrl"], suppress_origin=True, timeout=3)
            
            def send(method, params):
                msg_id = random.randint(1, 1000000)
                ws.send(json.dumps({"id": msg_id, "method": method, "params": params}))
                while True:
                    resp = json.loads(ws.recv())
                    if resp.get("id") == msg_id: return resp

            resp = send("Runtime.evaluate", {"expression": js_code, "returnByValue": True})
            ws.close()
            
            data_val = resp.get("result", {}).get("result", {}).get("value")
            if data_val:
                data = json.loads(data_val)
                data["tab_title"] = tab.get("title", "No Title")
                results.append(data)
        except Exception as e:
            results.append({"error": str(e), "tab": tab.get("title")})

    return results

def log_to_csv(data, filename="trading_log.csv"):
    if not isinstance(data, list) or not data:
        return
    
    file_exists = os.path.isfile(filename)
    
    # Flatten data for CSV
    rows = []
    all_fields = set(['timestamp', 'symbol', 'price', 'timeframe'])
    
    for entry in data:
        if "error" in entry: continue
        row = {
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'symbol': entry.get('symbol'),
            'price': entry.get('price'),
            'timeframe': entry.get('timeframe'),
        }
        # Add indicators
        indicators = entry.get('indicators', {})
        for name, val in indicators.items():
            row[f"ind_{name}"] = val
            all_fields.add(f"ind_{name}")
        rows.append(row)

    if not rows: return

    # Determine fieldnames (existing header + new indicators)
    fieldnames = sorted(list(all_fields))
    
    with open(filename, mode='a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for r in rows:
            for field in fieldnames:
                if field not in r: r[field] = None
            writer.writerow(r)
    print(f"✅ Logged {len(rows)} entries to {filename}")

if __name__ == "__main__":
    print("Fetching everything from all open tabs...")
    data = fetch_all_tv_prices()
    if isinstance(data, list):
        for entry in data:
            if "error" in entry:
                print(f"❌ Error in tab '{entry.get('tab')}': {entry['error']}")
                continue
            symbol = entry.get('symbol', '???')
            price = entry.get('price', '???')
            timeframe = entry.get('timeframe', '???')
            print(f"- {symbol} ({timeframe}) [Price: {price}]")
        
        log_to_csv(data)
    else:
        print(data)
