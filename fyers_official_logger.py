import os
import time
import json
import csv
from datetime import datetime
from fyers_apiv3 import fyersModel
from dotenv import load_dotenv

# Load credentials
load_dotenv()
CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
REDIRECT_URL = os.getenv("FYERS_REDIRECT_URL")

TOKEN_FILE = "fyers_token.json"
LOG_FILE = "fyers_official_log.csv"
SYMBOLS = ["NSE:RELIANCE-EQ", "NSE:TTKPRESTIG-EQ"]

# Memory to store last known values when market is closed
last_known_data = {}

def get_access_token(auth_code=None):
    # 1. Check if token already exists for today
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            token_data = json.load(f)
            if token_data.get("date") == datetime.now().strftime("%Y-%m-%d"):
                return token_data.get("access_token")

    # 2. If we have a new auth_code from the dashboard, use it
    if auth_code:
        session = fyersModel.SessionModel(
            client_id=CLIENT_ID,
            secret_key=SECRET_KEY,
            redirect_uri=REDIRECT_URL,
            response_type="code",
            grant_type="authorization_code"
        )
        session.set_token(auth_code)
        response = session.generate_access_token()
        
        if response.get("s") == "ok":
            access_token = response.get("access_token")
            with open(TOKEN_FILE, "w") as f:
                json.dump({"access_token": access_token, "date": datetime.now().strftime("%Y-%m-%d")}, f)
            print("✅ New token generated and saved.")
            return access_token
        else:
            print(f"❌ Error generating token: {response}")
            return None

    # 3. Otherwise, return the URL for the dashboard to show
    session = fyersModel.SessionModel(
        client_id=CLIENT_ID,
        secret_key=SECRET_KEY,
        redirect_uri=REDIRECT_URL,
        response_type="code",
        grant_type="authorization_code"
    )
    return session.generate_auth_url()

def log_to_csv(data):
    file_exists = os.path.isfile(LOG_FILE)
    rows = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    for item in data.get('d', []):
        symbol = item.get('n')
        v = item.get('v', {})
        
        # Logic: If field is missing (market closed), use the last known value
        if symbol not in last_known_data:
            last_known_data[symbol] = {'bq': 0, 'sq': 0, 'tbq': 0, 'tsq': 0, 'lp': 0, 'vol': 0}
        
        # Update only if new data exists
        curr = last_known_data[symbol]
        lp = v.get('lp', curr['lp'])
        vol = v.get('volume', curr['vol'])
        bq = v.get('bq', curr['bq'])
        sq = v.get('sq', curr['sq'])
        tbq = v.get('total_buy_qty', curr['tbq'])
        tsq = v.get('total_sell_qty', curr['tsq'])
        
        # Store back in memory
        last_known_data[symbol] = {'lp': lp, 'vol': vol, 'bq': bq, 'sq': sq, 'tbq': tbq, 'tsq': tsq}

        rows.append({
            'timestamp': ts,
            'symbol': symbol,
            'last_price': lp,
            'volume': vol,
            'buy_qty': bq,
            'sell_qty': sq,
            'total_buy_qty': tbq,
            'total_sell_qty': tsq
        })
        
    if not rows: return

    fieldnames = ['timestamp', 'symbol', 'last_price', 'volume', 'buy_qty', 'sell_qty', 'total_buy_qty', 'total_sell_qty']
    with open(LOG_FILE, mode='a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)
    print(f"✅ Logged {len(rows)} entries (Last Known State preserved).")

def main():
    access_token = get_access_token()
    if not access_token: return

    fyers = fyersModel.FyersModel(client_id=CLIENT_ID, token=access_token, log_path=os.getcwd())
    print(f"🚀 Fyers Logger started. Monitoring {SYMBOLS} every 1 minute...")

    while True:
        try:
            response = fyers.quotes({"symbols": ",".join(SYMBOLS)})
            if response.get('s') == 'ok':
                log_to_csv(response)
            else:
                print(f"⚠️  Fyers API Error: {response}")
        except Exception as e:
            print(f"❌ Error: {e}")
        time.sleep(60)

if __name__ == "__main__":
    main()
