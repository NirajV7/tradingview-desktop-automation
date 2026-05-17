import requests
import websocket
import json
import time
import random
import csv
import os
from datetime import datetime
import config

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

def get_last_logged_bucket_from_csv(filename, symbol):
    if not os.path.exists(filename) or os.stat(filename).st_size == 0:
        return None
    try:
        with open(filename, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if not rows: return None
            # Filter rows for this specific symbol
            symbol_rows = [r for r in rows if r.get('symbol') == symbol]
            if not symbol_rows: return None
            last_row = symbol_rows[-1]
            ts_str = last_row.get('timestamp')
            if ts_str:
                dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                epoch = int(dt.timestamp())
                return epoch
    except Exception as e:
        print(f"Error reading last bucket from {filename}: {e}")
    return None

def log_to_csv(data, filename="trading_log.csv"):
    if not isinstance(data, list) or not data:
        return
    
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

    # Determine fieldnames (align with existing header to prevent column shift-left bugs)
    if os.path.exists(filename) and os.stat(filename).st_size > 0:
        try:
            with open(filename, mode='r') as f:
                header = f.readline().strip()
                fieldnames = [col.strip() for col in header.split(',') if col.strip()]
            # Ensure any newly discovered indicators are appended to the fieldnames
            for field in sorted(list(all_fields)):
                if field not in fieldnames:
                    fieldnames.append(field)
        except Exception as e:
            print(f"CSV Header alignment fallback: {e}")
            fieldnames = sorted(list(all_fields))
    else:
        fieldnames = sorted(list(all_fields))
    
    # DYNAMIC CHECK: Does file need headers?
    file_needs_header = not os.path.exists(filename) or os.stat(filename).st_size == 0
    
    with open(filename, mode='a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if file_needs_header:
            writer.writeheader()
        for r in rows:
            for field in fieldnames:
                if field not in r: r[field] = None
            writer.writerow(r)
    print(f"✅ Logged {len(rows)} entries to {filename}")

if __name__ == "__main__":
    WATCHLIST_FILE = config.WATCHLIST_FILE
    last_logged_5m = {}
    last_logged_15m = {}

    # Loop Forever
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 TV Price Engine Started. Polling every 15s...")
    while True:
        try:
            watchlist = []
            if os.path.exists(WATCHLIST_FILE):
                with open(WATCHLIST_FILE, "r") as f:
                    watchlist = json.load(f)
            
            watchlist_clean = [s.split(":")[1].split("-")[0] if ":" in s else s for s in watchlist]

            data = fetch_all_tv_prices()
            if isinstance(data, list):
                found_symbols = []
                for entry in data:
                    if "error" in entry: continue
                    symbol = entry.get('symbol', '???')
                    found_symbols.append(symbol)
                
                # 1. Log to the high-frequency micro CSV
                log_to_csv(data, filename=config.TRADING_LOG)
                
                # 2. Log to the 5M and 15M closed candle CSVs upon Epoch Crossover
                now_epoch = int(time.time())
                bucket_5m = now_epoch - (now_epoch % 300)
                bucket_15m = now_epoch - (now_epoch % 900)
                
                for entry in data:
                    if "error" in entry: continue
                    sym = entry.get('symbol')
                    if not sym: continue
                    
                    tf = str(entry.get('timeframe', ''))
                    
                    if tf == "5":
                        if sym not in last_logged_5m:
                            last_logged_5m[sym] = get_last_logged_bucket_from_csv(config.TRADING_LOG_5M, sym)
                        
                        if last_logged_5m[sym] is None or bucket_5m > last_logged_5m[sym]:
                            log_to_csv([entry], filename=config.TRADING_LOG_5M)
                            last_logged_5m[sym] = bucket_5m
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] 📈 [TV 5M BUCKET CLOSE] Logged for {sym}")
                            
                    elif tf == "15":
                        if sym not in last_logged_15m:
                            last_logged_15m[sym] = get_last_logged_bucket_from_csv(config.TRADING_LOG_15M, sym)
                        
                        if last_logged_15m[sym] is None or bucket_15m > last_logged_15m[sym]:
                            log_to_csv([entry], filename=config.TRADING_LOG_15M)
                            last_logged_15m[sym] = bucket_15m
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] 📈 [TV 15M BUCKET CLOSE] Logged for {sym}")

                print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Logged {len(found_symbols)} TV entries.", flush=True)
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ TV Error: {data}", flush=True)
            
        except Exception as e:
            print(f"Loop Error: {e}")
            
        time.sleep(15)
