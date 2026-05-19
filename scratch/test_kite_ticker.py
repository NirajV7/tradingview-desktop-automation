"""
test_kite_ticker.py — Standalone KiteTicker WebSocket test
Reads existing Kite session, subscribes to open position tokens,
prints live ticks for 30 seconds. ZERO changes to existing code.
"""

import os
import sys
import json
import time
from datetime import datetime

# ── Path setup so we can reuse config.py ─────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kiteconnect import KiteConnect, KiteTicker
from config import KITE_TOKEN_FILE, KITE_API_KEY

# ── 1. Load access token ──────────────────────────────────────────────────────
if not os.path.exists(KITE_TOKEN_FILE):
    print("❌ No Kite token file found. Please authorize from the dashboard first.")
    sys.exit(1)

with open(KITE_TOKEN_FILE, "r") as f:
    token_data = json.load(f)

access_token = token_data.get("access_token")
if not access_token:
    print("❌ access_token missing in token file. Re-authorize Kite.")
    sys.exit(1)

print(f"✅ Kite token loaded (date: {token_data.get('date', 'unknown')})")

# ── 2. Init KiteConnect + fetch open positions ────────────────────────────────
kite = KiteConnect(api_key=KITE_API_KEY)
kite.set_access_token(access_token)

print("\n📡 Fetching open positions...")
try:
    positions = kite.positions()
    net_positions = [p for p in positions.get("net", []) if p.get("quantity", 0) != 0]
except Exception as e:
    print(f"❌ Failed to fetch positions: {e}")
    sys.exit(1)

if not net_positions:
    print("⚠️  No open positions found. Subscribing to NIFTY 50 index as fallback test.")
    # NSE:NIFTY 50 index token for testing
    instrument_tokens = [256265]
    token_symbol_map = {256265: "NIFTY 50"}
else:
    print(f"✅ Found {len(net_positions)} open position(s):")
    for p in net_positions:
        print(f"   {p['tradingsymbol']} | qty: {p['quantity']} | avg: ₹{p['average_price']} | ltp: ₹{p['last_price']} | pnl: ₹{p['pnl']:.2f}")

    # ── 3. Resolve instrument tokens ──────────────────────────────────────────
    symbols = [f"NSE:{p['tradingsymbol']}" for p in net_positions]
    print(f"\n🔍 Resolving instrument tokens for: {symbols}")
    try:
        ltp_data = kite.ltp(symbols)
    except Exception as e:
        print(f"❌ ltp() call failed: {e}")
        sys.exit(1)

    instrument_tokens = [v["instrument_token"] for v in ltp_data.values()]
    token_symbol_map = {v["instrument_token"]: k.replace("NSE:", "") for k, v in ltp_data.items()}

    print(f"✅ Resolved tokens: {token_symbol_map}")

# ── 4. Track state for PnL computation ───────────────────────────────────────
position_map = {p["tradingsymbol"]: p for p in net_positions} if net_positions else {}
live_ltp = {}
tick_count = 0
start_time = time.time()
DURATION_SECONDS = 30

# ── 5. KiteTicker callbacks ───────────────────────────────────────────────────
def on_ticks(ws, ticks):
    global tick_count
    tick_count += 1
    now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"\n{'─'*60}")
    print(f"  🕐 {now}  |  tick #{tick_count}")
    for tick in ticks:
        token = tick["instrument_token"]
        symbol = token_symbol_map.get(token, str(token))
        ltp = tick.get("last_price", 0.0)
        live_ltp[symbol] = ltp

        pos = position_map.get(symbol)
        if pos:
            qty = pos["quantity"]
            avg = pos["average_price"]
            buy_val = pos.get("buy_value", 0.0)
            sell_val = pos.get("sell_value", 0.0)
            # Same formula as dashboard_app.py
            if qty != 0:
                live_pnl = (sell_val - buy_val) + (qty * ltp)
            else:
                live_pnl = sell_val - buy_val
            pnl_str = f"+₹{live_pnl:.2f}" if live_pnl >= 0 else f"-₹{abs(live_pnl):.2f}"
            color = "\033[92m" if live_pnl >= 0 else "\033[91m"
            reset = "\033[0m"
            print(f"  {symbol:<15} LTP: ₹{ltp:<10.2f} PnL: {color}{pnl_str}{reset}")
        else:
            # Fallback (NIFTY index or no position)
            print(f"  {symbol:<15} LTP: ₹{ltp:.2f}")

    elapsed = time.time() - start_time
    if elapsed >= DURATION_SECONDS:
        print(f"\n✅ {DURATION_SECONDS}s test complete. Got {tick_count} ticks. WebSocket works!\n")
        ws.close()

def on_connect(ws, response):
    print(f"\n✅ WebSocket CONNECTED")
    ws.subscribe(instrument_tokens)
    ws.set_mode(ws.MODE_FULL, instrument_tokens)
    print(f"📡 Subscribed to {instrument_tokens} in FULL mode")
    print(f"⏳ Listening for {DURATION_SECONDS} seconds...\n")

def on_close(ws, code, reason):
    print(f"\n🔌 WebSocket CLOSED: code={code} reason={reason}")

def on_error(ws, code, reason):
    print(f"\n❌ WebSocket ERROR: code={code} reason={reason}")

def on_reconnect(ws, attempts_count):
    print(f"🔄 Reconnecting... attempt #{attempts_count}")

def on_noreconnect(ws):
    print("❌ Max reconnect attempts reached. Test failed.")

# ── 6. Connect and run ───────────────────────────────────────────────────────
print(f"\n🚀 Connecting KiteTicker WebSocket...")
kws = KiteTicker(KITE_API_KEY, access_token)
kws.on_ticks     = on_ticks
kws.on_connect   = on_connect
kws.on_close     = on_close
kws.on_error     = on_error
kws.on_reconnect = on_reconnect
kws.on_noreconnect = on_noreconnect

# reconnect=False so it stops cleanly after our test
kws.connect(threaded=False)
