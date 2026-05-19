from flask import Flask, render_template_string, redirect, url_for, request, jsonify, flash
import subprocess
import os
import csv
import json
import requests
import websocket
import random
import time
import base64
from datetime import datetime
from fyers_apiv3 import fyersModel
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = "nj_secret_key" # Required for flashing messages

CWD = "/Users/nj/.gemini/antigravity/scratch/trading-automation/"
TOKEN_FILE = os.path.join(CWD, "fyers_token.json")
WATCHLIST_FILE = os.path.join(CWD, "watchlist.json")
MASTER_CSV = os.path.join(CWD, "fyers_nse_cm.csv")
VENV_PYTHON = os.path.join(CWD, "venv/bin/python3")
CDP_URL = "http://localhost:9222/json"
TRADING_LOG = os.path.join(CWD, "trading_log.csv")
FYERS_LOG = os.path.join(CWD, "fyers_official_log.csv")
ENGINE_LOG = os.path.join(CWD, "engine.log")

def is_running(script_name):
    try:
        # Use pgrep -f to find the exact script running in the background
        # This is much more accurate than ps | grep
        cmd = f"pgrep -f '{script_name}'"
        subprocess.check_output(cmd, shell=True)
        return True
    except:
        return False

def get_tab_info(ws_url):
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
        if isinstance(val, str): val = json.loads(val)
        sym = val.get("symbol", "UNKNOWN").split(":")[-1].strip().upper()
        return sym, val.get("interval", "UNKNOWN")
    except:
        return "UNKNOWN", "UNKNOWN"

# Load Master Symbols for Search
MASTER_SYMBOLS = []
if os.path.exists(MASTER_CSV):
    with open(MASTER_CSV, 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) > 13:
                # Name, FyersSymbol, Ticker
                MASTER_SYMBOLS.append({
                    "name": row[1],
                    "fyers": row[9],
                    "ticker": row[13]
                })

CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
REDIRECT_URL = os.getenv("FYERS_REDIRECT_URL")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>NJ Quant Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        body { background-color: #0d1117; color: #c9d1d9; font-family: 'Inter', sans-serif; text-align: center; margin: 0; padding: 20px; line-height: 1.5; }
        .grid { display: grid; grid-template-columns: 1.5fr 1fr; gap: 24px; max-width: 1300px; margin: 0 auto; }
        .card { background: #161b22; border-radius: 16px; border: 1px solid #30363d; padding: 24px; margin-bottom: 24px; position: relative; box-shadow: 0 4px 12px rgba(0,0,0,0.3); transition: transform 0.2s; }
        .card:hover { border-color: #58a6ff; }
        .data-box { background: #010409; padding: 20px; border-radius: 12px; font-family: 'JetBrains Mono', monospace; font-size: 1.1em; border: 1px solid #238636; color: #39ff14; min-height: 120px; text-align: left; box-shadow: inset 0 0 10px rgba(57,255,20,0.1); }
        .btn { display: inline-flex; align-items: center; justify-content: center; padding: 12px 20px; margin: 5px; border-radius: 8px; font-weight: 600; cursor: pointer; text-decoration: none; color: white; border: none; font-size: 0.9em; transition: all 0.2s ease; }
        .btn:active { transform: scale(0.98); }
        .btn-blue { background: linear-gradient(135deg, #1f6feb, #0969da); }
        .btn-green { background: linear-gradient(135deg, #238636, #2ea043); }
        .btn-purple { background: linear-gradient(135deg, #8957e5, #a371f7); }
        .btn-red { background: linear-gradient(135deg, #da3633, #f85149); }
        .btn-gray { background: #30363d; }
        .btn:hover { filter: brightness(1.2); box-shadow: 0 0 15px rgba(255,255,255,0.1); }
        
        input, textarea { padding: 14px; border-radius: 10px; border: 1px solid #30363d; background: #0d1117; color: white; width: 92%; margin-bottom: 12px; font-size: 0.95em; outline: none; transition: border-color 0.2s; }
        input:focus, textarea:focus { border-color: #1f6feb; }
        textarea { height: 140px; font-family: monospace; }
        .symbol-tag { display: inline-flex; align-items: center; background: rgba(88, 166, 255, 0.1); padding: 8px 14px; border-radius: 10px; margin: 6px; border: 1px solid rgba(88, 166, 255, 0.3); font-size: 0.9em; color: #58a6ff; font-weight: 600; }
        .remove-btn { margin-left: 10px; cursor: pointer; color: #da3633; font-weight: bold; font-size: 1.2em; display: inline-block; transition: 0.2s; }
        .remove-btn:hover { color: #f85149; transform: scale(1.2); }
        
        /* Search Dropdown Styles */
        #search-results {
            position: absolute;
            top: 100%;
            left: 4%;
            width: 92%;
            background: #1c2128;
            border: 1px solid #444c56;
            border-radius: 12px;
            z-index: 1000;
            max-height: 350px;
            overflow-y: auto;
            display: none;
            text-align: left;
            box-shadow: 0 12px 30px rgba(0,0,0,0.6);
        }
        .search-item {
            padding: 12px 16px;
            border-bottom: 1px solid #30363d;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .search-item:last-child { border-bottom: none; }
        .search-item:hover { background: #1f6feb; }
        .search-item .ticker { color: #58a6ff; font-weight: 700; font-size: 1.05em; }
        .search-item .name { font-size: 0.8em; color: #8b949e; max-width: 60%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .search-item:hover .ticker, .search-item:hover .name { color: white; }
        
        /* Console Styles */
        .console-card { background: #010409; border: 1px solid #30363d; border-radius: 12px; padding: 15px; text-align: left; margin-top: 24px; }
        /* Table Styles */
        .watchlist-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        .watchlist-table th { text-align: left; padding: 12px; font-size: 0.75em; color: #8b949e; text-transform: uppercase; border-bottom: 1px solid #30363d; }
        .watchlist-table td { padding: 12px; font-size: 0.9em; border-bottom: 1px solid #21262d; vertical-align: middle; }
        .sym-name { font-weight: bold; color: #58a6ff; }
        .price-val { font-family: 'JetBrains Mono', monospace; }
        .trend-badge { padding: 4px 8px; border-radius: 6px; font-weight: bold; font-size: 0.8em; }
        .trend-bull { background: rgba(35, 134, 54, 0.2); color: #3fb950; border: 1px solid #238636; }
        .trend-bear { background: rgba(248, 81, 73, 0.2); color: #ff7b72; border: 1px solid #da3633; }
        .trend-neut { background: rgba(139, 148, 158, 0.1); color: #8b949e; border: 1px solid #30363d; }
        .console-title { font-size: 0.85em; font-weight: bold; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; }
        .console-window { height: 180px; overflow-y: auto; font-family: 'JetBrains Mono', monospace; font-size: 0.8em; color: #7ee787; line-height: 1.6; white-space: pre-wrap; padding-right: 10px; }
        .console-window::-webkit-scrollbar { width: 6px; }
        .console-window::-webkit-scrollbar-thumb { background: #30363d; border-radius: 10px; }
        .heartbeat { font-size: 0.75em; color: #8b949e; margin-left: 10px; font-weight: normal; }
        
        /* Toast Notifications */
        #toast-container { position: fixed; top: 20px; right: 20px; z-index: 9999; }
        .toast {
            background: rgba(30, 41, 59, 0.95);
            border-left: 4px solid #3b82f6;
            color: white;
            padding: 15px 25px;
            margin-bottom: 10px;
            border-radius: 8px;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.5);
            backdrop-filter: blur(10px);
            animation: slideIn 0.3s ease-out;
            display: flex;
            align-items: center;
            gap: 12px;
            font-weight: 500;
        }
        .toast.success { border-left-color: #10b981; }
        .toast.error { border-left-color: #ef4444; }
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }

        /* Status LEDs */
        .status-dot { height: 10px; width: 10px; border-radius: 50%; display: inline-block; margin-right: 8px; background-color: #30363d; border: 1px solid rgba(255,255,255,0.1); transition: all 0.3s; }
        .status-dot.active { background-color: #39ff14; box-shadow: 0 0 10px #39ff14; animation: pulse 1.5s infinite; }
        @keyframes pulse {
            0% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.2); opacity: 0.7; }
            100% { transform: scale(1); opacity: 1; }
        }
    </style>
    <script>
        function showToast(message, type = 'success') {
            const container = document.getElementById('toast-container');
            if (!container) return;
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            toast.innerHTML = (type === 'success' ? '✅ ' : '❌ ') + message;
            container.appendChild(toast);
            setTimeout(() => {
                toast.style.opacity = '0';
                toast.style.transform = 'translateX(100%)';
                toast.style.transition = 'all 0.5s ease';
                setTimeout(() => toast.remove(), 500);
            }, 4000);
        }

        setInterval(function(){
            fetch('/api/data').then(r => r.json()).then(d => {
                document.getElementById('signal-rows').innerHTML = d.html;
            });
            // Update Status LEDs
            fetch('/api/status').then(r => r.json()).then(d => {
                document.getElementById('dot-tv').className = d.tv ? 'status-dot active' : 'status-dot';
                document.getElementById('dot-fyers').className = d.fyers ? 'status-dot active' : 'status-dot';
                document.getElementById('dot-log').className = d.log ? 'status-dot active' : 'status-dot';
            });
            // Update Console
            fetch('/api/logs').then(r => r.json()).then(data => {
                const con = document.getElementById('console-output');
                if (!con) return;
                const wasAtBottom = con.scrollHeight - con.clientHeight <= con.scrollTop + 1;
                con.innerText = data.logs || "> Waiting for engine output...";
                if (wasAtBottom) con.scrollTop = con.scrollHeight;
            });
        }, 2000);

        function searchStocks(q) {
            const results = document.getElementById('search-results');
            if (q.length < 2) {
                results.style.display = 'none';
                return;
            }
            fetch(`/api/search?q=${q}`)
                .then(r => r.json())
                .then(data => {
                    results.innerHTML = '';
                    if (data.length > 0) {
                        data.forEach(item => {
                            const div = document.createElement('div');
                            div.className = 'search-item';
                            div.innerHTML = `<span class="ticker">${item.ticker}</span> <span class="name">${item.name}</span>`;
                            div.onclick = () => selectStock(item.fyers);
                            results.appendChild(div);
                        });
                        results.style.display = 'block';
                    } else {
                        results.style.display = 'none';
                    }
                });
        }

        function selectStock(symbol) {
            fetch('/api/add_symbol', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({symbol: symbol})
            }).then(() => window.location.reload());
        }
        function removeStock(symbol) {
            fetch('/api/remove_symbol', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({symbol: symbol})
            }).then(() => window.location.reload());
        }
    </script>
</head>
<body>
    <div id="toast-container"></div>
    <script>
        window.addEventListener('DOMContentLoaded', () => {
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        showToast("{{ message }}", "{{ 'success' if category != 'error' else 'error' }}");
                    {% endfor %}
                {% endif %}
            {% endwith %}
        });
    </script>
    <h1>🚀 NJ QUANT TERMINAL</h1>
    
    <div class="grid">
        <div class="main-content">
            <div class="card" style="grid-column: span 2;">
                <h3>📊 Live Signal Grid</h3>
                <div id="data-content">
                    <table class="watchlist-table">
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Fyers Price</th>
                                <th>5m Wave</th>
                                <th>15m Tide</th>
                                <th>Trend Signal</th>
                            </tr>
                        </thead>
                        <tbody id="signal-rows">
                            <tr><td colspan="5" style="text-align:center; padding: 40px; color:#8b949e;">[ WAITING FOR SYSTEM HEARTBEAT ]</td></tr>
                        </tbody>
                    </table>
                </div>
                <!-- Sleek Trend Rules Legend -->
                <div class="legend-box" style="margin-top: 20px; text-align: left; padding: 16px 20px; background: rgba(13, 17, 23, 0.6); border: 1px solid #30363d; border-radius: 12px; font-size: 0.82em; color: #8b949e; line-height: 1.5;">
                    <div style="font-weight: 700; color: #c9d1d9; margin-bottom: 10px; display: flex; align-items: center; gap: 6px; font-size: 0.95em;">
                        🔍 Trend State Logic & Confirmation Rules
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                        <div>
                            <strong style="color: #3fb950; display: inline-flex; align-items: center; gap: 4px;">🟢 BULLISH SETUP (All 4 Met)</strong>
                            <ul style="margin: 6px 0 0 12px; padding: 0; list-style-type: none;">
                                <li>• Price &gt; VWAP <span style="font-size:0.85em; color:#58a6ff;">(Institutional baseline)</span></li>
                                <li>• 20 EMA &gt; 50 EMA <span style="font-size:0.85em; color:#58a6ff;">(Bullish structure)</span></li>
                                <li>• Price &gt; 200 EMA <span style="font-size:0.85em; color:#58a6ff;">(Macro anchor)</span></li>
                                <li>• RSI &gt; 50 <span style="font-size:0.85em; color:#58a6ff;">(Buying momentum)</span></li>
                                <li style="margin-top:4px;"><strong style="color: #d29922;">⚠️ OVERBOUGHT:</strong> Bullish met + RSI &gt; 70</li>
                            </ul>
                        </div>
                        <div>
                            <strong style="color: #f85149; display: inline-flex; align-items: center; gap: 4px;">🔴 BEARISH SETUP (All 4 Met)</strong>
                            <ul style="margin: 6px 0 0 12px; padding: 0; list-style-type: none;">
                                <li>• Price &lt; VWAP <span style="font-size:0.85em; color:#ff7b72;">(Institutional baseline)</span></li>
                                <li>• 20 EMA &lt; 50 EMA <span style="font-size:0.85em; color:#ff7b72;">(Bearish structure)</span></li>
                                <li>• Price &lt; 200 EMA <span style="font-size:0.85em; color:#ff7b72;">(Macro anchor)</span></li>
                                <li>• RSI &lt; 50 <span style="font-size:0.85em; color:#ff7b72;">(Selling momentum)</span></li>
                                <li style="margin-top:4px;"><strong style="color: #d29922;">⚠️ OVERSOLD:</strong> Bearish met + RSI &lt; 30</li>
                            </ul>
                        </div>
                    </div>
                    <div style="margin-top: 10px; border-top: 1px solid rgba(48, 54, 61, 0.5); padding-top: 10px;">
                        <strong style="color: #8b949e;">🟡 CONGESTION:</strong> Indicators or timeframes are conflicting, representing a sideways or choppy structure.
                    </div>
                </div>
            </div>

            <div class="card">
                <h3>⚙️ Engine Controls</h3>
                <div style="display: flex; flex-direction: column; align-items: stretch; gap: 10px;">
                    <div style="display: flex; align-items: center; justify-content: space-between; background: #0d1117; padding: 10px 15px; border-radius: 10px; border: 1px solid #30363d;">
                        <span><span id="dot-tv" class="status-dot"></span> TradingView App</span>
                        <a href="/start_tv" class="btn btn-blue" style="margin:0; padding: 8px 15px;">OPEN</a>
                    </div>
                    <div style="display: flex; align-items: center; justify-content: space-between; background: #0d1117; padding: 10px 15px; border-radius: 10px; border: 1px solid #30363d;">
                        <span><span id="dot-fyers" class="status-dot"></span> Fyers Engine <span id="timer-fyers" class="heartbeat"></span></span>
                        <a href="/start_fyers" class="btn btn-green" style="margin:0; padding: 8px 15px;">START</a>
                    </div>
                    <div style="display: flex; align-items: center; justify-content: space-between; background: #0d1117; padding: 10px 15px; border-radius: 10px; border: 1px solid #30363d;">
                        <span><span id="dot-log" class="status-dot"></span> TV Price Logs <span id="timer-log" class="heartbeat"></span></span>
                        <a href="/start_tv_log" class="btn btn-purple" style="margin:0; padding: 8px 15px;">START</a>
                    </div>
                    <div style="display: flex; gap: 10px; margin-top: 5px;">
                        <a href="/sync_tabs" class="btn btn-blue" style="flex: 2; margin:0; background: linear-gradient(135deg, #0052D4, #4364F7, #6FB1FC);">SYNC TABS</a>
                        <a href="/stop" class="btn btn-red" style="flex: 1; margin:0;">STOP ALL</a>
                    </div>
                    <div style="margin-top: 10px;">
                        <a href="/clear_logs" class="btn btn-gray" style="width: 100%; margin:0; border: 1px solid #444c56; background: #21262d;">🧹 WIPE ALL LOGS</a>
                    </div>
                </div>
            </div>

            <div class="console-card">
                <div class="console-header">
                    <span class="console-title">🛰️ System Live Console</span>
                    <span style="font-size: 0.7em; color: #238636;">● STREAMING</span>
                </div>
                <div id="console-output" class="console-window">Initializing satellite uplink...</div>
            </div>

            <div class="card">
                <h3>🔑 Fyers API Authorization</h3>
                {% if needs_login %}
                    <p style="color: #da3633;">🔴 TOKEN EXPIRED</p>
                    <a href="{{ auth_url }}" target="_blank" class="btn btn-blue">Get Login Code</a>
                    <form action="/auth" method="POST" style="margin-top: 15px;">
                        <input type="text" name="auth_code" placeholder="Paste Auth Code..." required>
                        <button type="submit" class="btn btn-green">Authorize</button>
                    </form>
                {% else %}
                    <p style="color: #238636;">✅ TOKEN ACTIVE (Good for today)</p>
                {% endif %}
            </div>
        </div>

        <div class="side-col">
            <div class="card" style="overflow: visible;">
                <h3 style="margin-top: 0;">🔍 Add Stock</h3>
                <input type="text" id="stock-search" placeholder="Search Company or Ticker..." onkeyup="searchStocks(this.value)" autocomplete="off">
                <div id="search-results"></div>
                <p style="font-size: 0.75em; color: #8b949e; margin-top: 5px;">Uses Fyers Master Symbol List</p>
            </div>

            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                    <h3 style="margin: 0;">📋 Active Watchlist</h3>
                    <span style="background: #238636; color: white; padding: 4px 12px; border-radius: 12px; font-size: 0.8em; font-weight: bold;">{{ symbols_list|length }} STOCKS</span>
                </div>
                
                <div style="text-align: left; max-height: 400px; overflow-y: auto;">
                    {% if not symbols_list %}
                        <p style="color: #8b949e; text-align: center; font-style: italic;">No stocks added yet.</p>
                    {% endif %}
                    {% for sym in symbols_list %}
                        <div class="symbol-tag">
                            {{ sym }}
                            <span class="remove-btn" onclick="removeStock('{{ sym }}')" title="Remove">×</span>
                        </div>
                    {% endfor %}
                </div>

                {% if symbols_list %}
                    <a href="/clear_watchlist" class="btn btn-red" style="width: 100%; margin-top: 20px; background: transparent; border: 1px solid #da3633; color: #da3633;">Clear All</a>
                {% endif %}
            </div>
        </div>
    </div>
</body>
</html>
"""

def check_auth():
    # Helper to generate URL
    def get_new_url():
        session = fyersModel.SessionModel(
            client_id=CLIENT_ID, secret_key=SECRET_KEY, redirect_uri=REDIRECT_URL,
            response_type="code", grant_type="authorization_code"
        )
        return session.generate_authcode()

    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            try:
                token_data = json.load(f)
                # 1. Check Date
                if token_data.get("date") != datetime.now().strftime("%Y-%m-%d"):
                    return True, get_new_url()
                
                # 2. Check JWT Expiry
                token = token_data.get("access_token", "")
                if token:
                    parts = token.split('.')
                    if len(parts) >= 2:
                        payload_b64 = parts[1]
                        payload_b64 += '=' * (-len(payload_b64) % 4)
                        payload_data = json.loads(base64.b64decode(payload_b64).decode('utf-8'))
                        exp = payload_data.get('exp')
                        if exp and datetime.now().timestamp() > exp:
                            return True, get_new_url()
                
                return False, None
            except Exception as e:
                print(f"Auth Check Error: {e}")
                return True, get_new_url()
    
    return True, get_new_url()

@app.route('/')
def index():
    needs_login, auth_url = check_auth()
    
    # Load current watchlist
    symbols_list = []
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r") as f:
            symbols_list = json.load(f)
    
    current_symbols_text = ", ".join([s.split(":")[1].split("-")[0] if ":" in s else s for s in symbols_list])
    
    return render_template_string(
        HTML_TEMPLATE, 
        needs_login=needs_login, 
        auth_url=auth_url,
        symbols_list=symbols_list,
        current_symbols=current_symbols_text
    )

@app.route('/update_watchlist', methods=['POST'])
def update_watchlist():
    raw_text = request.form.get('symbols', '')
    # Logic: comma, space, or newline separated
    raw_list = raw_text.replace(',', ' ').split()
    valid_symbols = []
    for s in raw_list:
        s = s.strip().upper()
        if not s: continue
        # Normalize to Fyers Format
        if ":" not in s:
            s = f"NSE:{s}"
        if "-" not in s and "INDEX" not in s:
            s = f"{s}-EQ"
        valid_symbols.append(s)
    
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(list(set(valid_symbols)), f)
        
    return redirect(url_for('index'))

@app.route('/api/search')
def search():
    query = request.args.get('q', '').upper()
    if not query:
        return jsonify([])
    
    results = []
    for s in MASTER_SYMBOLS:
        if query in s['ticker'] or query in s['name']:
            results.append(s)
        if len(results) >= 10: # Limit results
            break
    return jsonify(results)

@app.route('/api/add_symbol', methods=['POST'])
def add_symbol():
    data = request.get_json()
    symbol = data.get('symbol')
    
    symbols_list = []
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r") as f:
            symbols_list = json.load(f)
    
    if symbol not in symbols_list:
        symbols_list.append(symbol)
        with open(WATCHLIST_FILE, "w") as f:
            json.dump(symbols_list, f)
    
    return jsonify({"status": "ok"})

@app.route('/api/remove_symbol', methods=['POST'])
def remove_symbol():
    data = request.get_json()
    symbol = data.get('symbol')
    
    symbols_list = []
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r") as f:
            symbols_list = json.load(f)
    
    if symbol in symbols_list:
        symbols_list.remove(symbol)
        with open(WATCHLIST_FILE, "w") as f:
            json.dump(symbols_list, f)
    
    return jsonify({"status": "ok"})

@app.route('/clear_watchlist')
def clear_watchlist():
    with open(WATCHLIST_FILE, "w") as f:
        json.dump([], f)
    return redirect(url_for('index'))

@app.route('/api/data')
def api_data():
    active_symbols = []
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r") as f:
            active_symbols = json.load(f)
            
    # Normalize symbols for comparison
    active_names = [s.split(":")[1].split("-")[0] if ":" in s else s for s in active_symbols]
    data_map = {} # { symbol: { "5": price, "15": price, "last_price": p } }

    # 1. Get Official Prices from Fyers Log
    if os.path.exists(FYERS_LOG):
        try:
            with open(FYERS_LOG, "r") as f:
                lines = f.readlines()
                if len(lines) > 1:
                    reader = csv.DictReader(lines)
                    for row in reader:
                        sym = row.get('symbol', '')
                        name = sym.split(":")[1].split("-")[0] if ":" in sym else sym
                        if name in active_names:
                            if name not in data_map: data_map[name] = {}
                            data_map[name]['lp'] = row.get('last_price', '...')
        except: pass

    # 2. Get Timeframe Data from TV Log
    if os.path.exists(TRADING_LOG):
        try:
            with open(TRADING_LOG, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row.get('symbol')
                    if name in active_names:
                        if name not in data_map: data_map[name] = {}
                        tf = str(row.get('timeframe'))
                        data_map[name][tf] = row.get('price')
                        
                        for col_key, val in row.items():
                            if val is None or val == "":
                                continue
                            k = col_key.lower()
                            if "vwap" in k or "volume weighted average price" in k:
                                data_map[name][f"{tf}_vwap"] = val
                            elif "exponential(200)" in k or k == "ind_moving average exponential":
                                data_map[name][f"{tf}_ema200"] = val
                            elif "exponential(50)" in k or "moving average exponential 2" in k:
                                data_map[name][f"{tf}_ema50"] = val
                            elif "exponential(20)" in k or "moving average exponential 3" in k:
                                data_map[name][f"{tf}_ema20"] = val
                            elif "rsi" in k or "relative strength index" in k:
                                data_map[name][f"{tf}_rsi"] = val
        except: pass

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

    # Build HTML table rows
    html = ""
    for name in active_names:
        d = data_map.get(name, {})
        p5 = d.get('5', '...')
        p15 = d.get('15', '...')
        lp = d.get('lp', '...')
        
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
    
    return {"html": html or '<tr><td colspan="5" style="text-align:center; color:#8b949e;">[ NO DATA ]</td></tr>'}

@app.route('/api/status')
def api_status():
    tv_open = False
    try:
        res = requests.get(CDP_URL, timeout=0.5)
        tv_open = (res.status_code == 200)
    except: pass
    
    return jsonify({
        "tv": tv_open,
        "fyers": is_running("fyers_official_logger.py"),
        "log": is_running("fetch_price.py")
    })

@app.route('/auth', methods=['POST'])
def auth():
    auth_code = request.form.get('auth_code', '').strip()
    
    # If user pasted the whole URL, extract the code part
    if "auth_code=" in auth_code:
        auth_code = auth_code.split("auth_code=")[1].split("&")[0]
    
    session = fyersModel.SessionModel(
        client_id=CLIENT_ID, secret_key=SECRET_KEY, redirect_uri=REDIRECT_URL,
        response_type="code", grant_type="authorization_code"
    )
    session.set_token(auth_code)
    response = session.generate_token()
    
    if response.get("s") == "ok":
        access_token = response.get("access_token")
        with open(TOKEN_FILE, "w") as f:
            json.dump({"access_token": access_token, "date": datetime.now().strftime("%Y-%m-%d")}, f)
    return redirect(url_for('index'))

def make_response(msg, msg_type, ajax=False):
    if ajax:
        return jsonify({"status": "success" if msg_type == "success" else "error", "message": msg})
    flash(msg, msg_type)
    return redirect(url_for('index'))

@app.route('/start_tv')
def start_tv():
    ajax = request.args.get('ajax', '0') == '1'
    try:
        response = requests.get(CDP_URL, timeout=1)
        if response.status_code == 200:
            return make_response("TradingView is ALREADY OPEN on Port 9222", "error", ajax)
    except:
        pass # Port is free, proceed with opening

    subprocess.run('open -a "TradingView" --args --remote-debugging-port=9222', shell=True)
    return make_response("TradingView Launch Command Sent", "success", ajax)

@app.route('/stop_tv')
def stop_tv():
    ajax = request.args.get('ajax', '0') == '1'
    try:
        subprocess.run("pkill -f TradingView", shell=True)
        return make_response("TradingView Closed Successfully", "success", ajax)
    except Exception as e:
        return make_response(f"Failed to close TradingView: {str(e)}", "error", ajax)

@app.route('/start_fyers')
def start_fyers():
    ajax = request.args.get('ajax', '0') == '1'
    if is_running("fyers_official_logger.py"):
        return make_response("Fyers Engine is ALREADY RUNNING", "error", ajax)
    else:
        with open(ENGINE_LOG, "a") as log_file:
            subprocess.Popen([VENV_PYTHON, os.path.join(CWD, "fyers_official_logger.py")], cwd=CWD, stdout=log_file, stderr=log_file)
        return make_response("Fyers Engine Started", "success", ajax)

@app.route('/stop_fyers')
def stop_fyers():
    ajax = request.args.get('ajax', '0') == '1'
    if not is_running("fyers_official_logger.py"):
        return make_response("Fyers Engine is already Stopped", "error", ajax)
    subprocess.run("pkill -f fyers_official_logger.py", shell=True)
    return make_response("Fyers Engine Stopped Successfully", "success", ajax)

@app.route('/start_tv_log')
def start_tv_log():
    ajax = request.args.get('ajax', '0') == '1'
    if is_running("fetch_price.py"):
        return make_response("TV Scraper is ALREADY RUNNING", "error", ajax)
    else:
        with open(ENGINE_LOG, "a") as log_file:
            subprocess.Popen([VENV_PYTHON, os.path.join(CWD, "fetch_price.py")], cwd=CWD, stdout=log_file, stderr=log_file)
        return make_response("TradingView Price Scraper Started", "success", ajax)

@app.route('/stop_tv_log')
def stop_tv_log():
    ajax = request.args.get('ajax', '0') == '1'
    if not is_running("fetch_price.py"):
        return make_response("TV Scraper is already Stopped", "error", ajax)
    subprocess.run("pkill -f fetch_price.py", shell=True)
    return make_response("TradingView Price Scraper Stopped Successfully", "success", ajax)

@app.route('/clear_logs')
def clear_logs():
    for f in [TRADING_LOG, FYERS_LOG, ENGINE_LOG]:
        if os.path.exists(f):
            os.remove(f)
    flash("All Logs Wiped!", "success")
    return redirect(url_for('index'))

@app.route('/api/logs')
def api_logs():
    if not os.path.exists(ENGINE_LOG):
        return jsonify({"logs": ""})
    try:
        # Overload Protection: If log > 1MB, clear it
        if os.path.getsize(ENGINE_LOG) > 1024 * 1024:
            with open(ENGINE_LOG, "w") as f:
                f.write(f"[{datetime.now().strftime('%H:%M:%S')}] ♻️ Log Rotated (Size exceeded 1MB)\n")
        
        with open(ENGINE_LOG, "r") as f:
            lines = f.readlines()
            last_lines = "".join(lines[-20:])
            return jsonify({"logs": last_lines})
    except:
        return jsonify({"logs": "Error reading logs..."})

@app.route('/sync_tabs')
def sync_tabs():
    if not os.path.exists(WATCHLIST_FILE): 
        flash("Watchlist file missing", "error")
        return redirect(url_for('index'))
    
    with open(WATCHLIST_FILE, "r") as f:
        watchlist_full = json.load(f)
    
    if not watchlist_full: 
        flash("Watchlist is empty", "error")
        return redirect(url_for('index'))

    try:
        response = requests.get(CDP_URL)
        tabs = [t for t in response.json() if "tradingview.com/chart" in t.get("url", "")]
        if not tabs: 
            flash("No active TradingView chart found. Open one manually first.", "error")
            return redirect(url_for('index'))
        
        # 1. Scan existing tabs for (Symbol, Interval) pairs
        open_pairs = []
        for t in tabs:
            sym, interval = get_tab_info(t.get("webSocketDebuggerUrl"))
            if sym != "UNKNOWN":
                open_pairs.append((sym, str(interval)))
        
        # 2. Open missing intervals (5 and 15)
        target_tab_ws = tabs[0].get("webSocketDebuggerUrl")
        ws = websocket.create_connection(target_tab_ws, suppress_origin=True, timeout=5)
        
        count = 0
        target_intervals = ["5", "15"]
        
        for full_sym in watchlist_full:
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
                time.sleep(1.5) # Slightly longer sleep to ensure order
        
        ws.close()
        if count > 0:
            flash(f"Opened {count} Dual-Timeframe Tabs", "success")
        else:
            flash("All 5m/15m Pairs Already Open", "success")
    except Exception as e:
        flash(f"Sync Failed: {str(e)}", "error")
    
    return redirect(url_for('index'))

@app.route('/start_all')
def start_all():
    ajax = request.args.get('ajax', '0') == '1'
    launched = 0
    
    # 1. TradingView app
    tv_running = False
    try:
        res = requests.get(CDP_URL, timeout=0.5)
        if res.status_code == 200:
            tv_running = True
    except:
        pass
    if not tv_running:
        subprocess.run('open -a "TradingView" --args --remote-debugging-port=9222', shell=True)
        launched += 1
        time.sleep(1.0)
        
    # 2. Fyers
    if not is_running("fyers_official_logger.py"):
        with open(ENGINE_LOG, "a") as log_file:
            subprocess.Popen([VENV_PYTHON, os.path.join(CWD, "fyers_official_logger.py")], cwd=CWD, stdout=log_file, stderr=log_file)
        launched += 1
        
    # 3. TV Price Logs scraper
    if not is_running("fetch_price.py"):
        with open(ENGINE_LOG, "a") as log_file:
            subprocess.Popen([VENV_PYTHON, os.path.join(CWD, "fetch_price.py")], cwd=CWD, stdout=log_file, stderr=log_file)
        launched += 1
        
    if launched > 0:
        return make_response(f"Successfully Started {launched} Stopped Components", "success", ajax)
    return make_response("All System Engines are already Active", "error", ajax)

@app.route('/stop')
def stop():
    ajax = request.args.get('ajax', '0') == '1'
    stopped = 0
    with open(ENGINE_LOG, "a") as log_file:
        log_file.write(f"[{datetime.now().strftime('%H:%M:%S')}] 🛑 STOP ALL COMMAND RECEIVED...\n")
        
    if is_running("fyers_official_logger.py"):
        subprocess.run("pkill -f fyers_official_logger.py", shell=True)
        stopped += 1
    if is_running("fetch_price.py"):
        subprocess.run("pkill -f fetch_price.py", shell=True)
        stopped += 1
        
    # Also close TradingView
    try:
        res = requests.get(CDP_URL, timeout=0.5)
        if res.status_code == 200:
            subprocess.run("pkill -f TradingView", shell=True)
            stopped += 1
    except:
        pass
    
    with open(ENGINE_LOG, "a") as log_file:
        log_file.write(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ System shutdown complete. {stopped} engines killed.\n")

    if stopped > 0:
        return make_response(f"Successfully Stopped {stopped} Components", "success", ajax)
    return make_response("All Components were already Stopped", "error", ajax)

if __name__ == "__main__":
    # Clean Startup: Kill any lingering engines before starting the dashboard
    print("🧹 Cleaning up old background engines...")
    subprocess.run("pkill -f fyers_official_logger.py", shell=True)
    subprocess.run("pkill -f fetch_price.py", shell=True)
    
    app.run(port=8080, debug=False)
