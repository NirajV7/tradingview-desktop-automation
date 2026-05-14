import requests
import websocket
import json
import time
import random

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
            
            data = json.loads(resp["result"]["result"]["value"])
            data["tab_title"] = tab.get("title", "No Title")
            results.append(data)
        except Exception as e:
            results.append({"error": str(e), "tab": tab.get("title")})

    return results

if __name__ == "__main__":
    print("Fetching everything from all open tabs...")
    data = fetch_all_tv_prices()
    if isinstance(data, list):
        for entry in data:
            symbol = entry.get('symbol', '???')
            price = entry.get('price', '???')
            timeframe = entry.get('timeframe', '???')
            tab = entry.get('tab_title', '???')
            print(f"\n- {symbol} ({timeframe}) [Price: {price}] [Tab: {tab}]")
            indicators = entry.get('indicators', {})
            for name, val in indicators.items():
                print(f"  > {name}: {val}")
    else:
        print(data)
