from flask import Flask, render_template_string, redirect, url_for, request
import os
import subprocess
import time
import json
from datetime import datetime
from fyers_apiv3 import fyersModel
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

CWD = "/Users/nj/.gemini/antigravity/scratch/trading-automation/"
FYERS_LOG = os.path.join(CWD, "fyers_official_log.csv")
TOKEN_FILE = os.path.join(CWD, "fyers_token.json")
VENV_PYTHON = os.path.join(CWD, "venv/bin/python3")

CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
REDIRECT_URL = os.getenv("FYERS_REDIRECT_URL")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>NJ Quant Dashboard</title>
    <style>
        body { background-color: #0d1117; color: #c9d1d9; font-family: sans-serif; text-align: center; }
        .container { max-width: 900px; margin: 30px auto; padding: 20px; background: #161b22; border-radius: 12px; border: 1px solid #30363d; }
        .data-box { background: #010409; padding: 20px; border-radius: 8px; font-family: monospace; font-size: 1.1em; border: 1px solid #238636; color: #39ff14; margin: 20px 0; }
        .btn { display: inline-block; padding: 12px 24px; margin: 5px; border-radius: 6px; font-weight: bold; cursor: pointer; text-decoration: none; color: white; border: none; }
        .btn-blue { background-color: #1f6feb; }
        .btn-green { background-color: #238636; }
        .btn-purple { background-color: #8957e5; }
        .btn-red { background-color: #da3633; }
        .login-card { background: #0d1117; padding: 20px; border-radius: 8px; margin-top: 30px; border: 1px solid #30363d; }
        input { padding: 10px; width: 300px; border-radius: 4px; border: 1px solid #30363d; background: #0d1117; color: white; }
    </style>
    <script>
        // Auto-refresh data every 5 seconds without reloading the whole page for buttons
        setInterval(function(){
            fetch('/api/data').then(r => r.json()).then(d => {
                document.getElementById('data-content').innerHTML = d.html;
            });
        }, 5000);
    </script>
</head>
<body>
    <div class="container">
        <h1>🚀 NJ QUANT TERMINAL</h1>
        
        <div class="data-box" id="data-content">
            [ LOADING LIVE DATA... ]
        </div>

        <div class="controls">
            <a href="/start_tv" class="btn btn-blue">1. OPEN TRADINGVIEW</a>
            <a href="/start_fyers" class="btn btn-green">2. START FYERS LOGGER</a>
            <a href="/start_tv_log" class="btn btn-purple">3. START TV LOGS</a>
            <a href="/stop" class="btn btn-red">🛑 STOP ALL</a>
        </div>

        <div class="login-card">
            <h3>🔑 Fyers API Authorization</h3>
            {% if needs_login %}
                <p>Status: <span style="color: #da3633;">🔴 TOKEN EXPIRED</span></p>
                <a href="{{ auth_url }}" target="_blank" class="btn btn-blue">Get Login Code</a>
                <form action="/auth" method="POST" style="margin-top: 15px;">
                    <input type="text" name="auth_code" placeholder="Paste Auth Code Here..." required>
                    <button type="submit" class="btn btn-green">Authorize</button>
                </form>
            {% else %}
                <p>Status: <span style="color: #238636;">✅ TOKEN ACTIVE</span></p>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

def check_auth():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            token_data = json.load(f)
            if token_data.get("date") == datetime.now().strftime("%Y-%m-%d"):
                return False, None
    
    session = fyersModel.SessionModel(
        client_id=CLIENT_ID, secret_key=SECRET_KEY, redirect_uri=REDIRECT_URL,
        response_type="code", grant_type="authorization_code"
    )
    return True, session.generate_auth_url()

@app.route('/')
def index():
    needs_login, auth_url = check_auth()
    return render_template_string(HTML_TEMPLATE, needs_login=needs_login, auth_url=auth_url)

@app.route('/api/data')
def api_data():
    html = "[ SYSTEM OFFLINE / WAITING FOR DATA ]"
    if os.path.exists(FYERS_LOG):
        with open(FYERS_LOG, "r") as f:
            lines = f.readlines()
            if len(lines) > 2:
                last_two = lines[-2:]
                html = "<div style='text-align:left; padding-left: 15%;'>"
                for line in last_two:
                    p = line.strip().split(',')
                    if len(p) >= 6:
                        html += f"🔹 {p[1]}: ₹{p[2]} | Vol: {p[3]} | Depth: {p[4]}/{p[5]}<br>"
                html += "</div>"
    return {"html": html}

@app.route('/auth', methods=['POST'])
def auth():
    auth_code = request.form.get('auth_code')
    session = fyersModel.SessionModel(
        client_id=CLIENT_ID, secret_key=SECRET_KEY, redirect_uri=REDIRECT_URL,
        response_type="code", grant_type="authorization_code"
    )
    session.set_token(auth_code)
    response = session.generate_access_token()
    
    if response.get("s") == "ok":
        access_token = response.get("access_token")
        with open(TOKEN_FILE, "w") as f:
            json.dump({"access_token": access_token, "date": datetime.now().strftime("%Y-%m-%d")}, f)
    return redirect(url_for('index'))

@app.route('/start_tv')
def start_tv():
    subprocess.run('open -a "TradingView" --args --remote-debugging-port=9222', shell=True)
    return redirect(url_for('index'))

@app.route('/start_fyers')
def start_fyers():
    subprocess.Popen([VENV_PYTHON, os.path.join(CWD, "fyers_official_logger.py")])
    return redirect(url_for('index'))

@app.route('/start_tv_log')
def start_tv_log():
    subprocess.Popen([VENV_PYTHON, os.path.join(CWD, "fetch_price.py")])
    return redirect(url_for('index'))

@app.route('/stop')
def stop():
    subprocess.run("pkill -f fyers_official_logger.py", shell=True)
    subprocess.run("pkill -f fetch_price.py", shell=True)
    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run(port=8080, debug=False)
