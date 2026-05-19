#!/usr/bin/env python3
"""
Quantitative Trading System: Zerodha Kite Execution Engine (Modular Orchestrator)
Path: trade_setup/kite_execution_engine.py

Description:
  Standalone, high-frequency execution script that uses Fyers telemetry logs 
  (fyers_indicators_5m.csv, fyers_official_log.csv) to evaluate intraday rules, 
  and executes trades on ZERODHA KITE using your ₹5 Lakh Risk Management rules.

  Features:
  - 100% Decoupled: Zero impact on your active Fyers caching and dashboard apps.
  - Safe Simulation: Includes a high-fidelity "Dry-Run" mode to test rules on live ticks.
  - Sizing Enforced: Dynamically sizes positions based on ₹2,500 Risk and SL width.
  - Double Defense: Automatically places Target (LMT) and Stop Loss (SL-M) orders on Kite.
"""

import os
import sys
import json
import time
import csv
from datetime import datetime
from dotenv import load_dotenv

# Ensure the root path is accessible for config imports
ROOT_DIR = "/Users/nj/.gemini/antigravity/scratch/trading-automation/"
sys.path.append(ROOT_DIR)

import config

# Load local .env (where Zerodha credentials reside)
load_dotenv(dotenv_path=os.path.join(config.CWD, ".env"))

# Import delegated methods from engine sub-modules
from trade_setup.engine.telemetry import (
    get_orb_range_from_logs,
    get_volume_baseline,
    get_volume_baseline_15m,
    get_tick_spread_volume,
    get_daily_open_price
)
from trade_setup.engine.costs import fetch_transaction_costs
from trade_setup.engine.journal import log_trade_to_journal
from trade_setup.engine.rules import evaluate_live_rules
from trade_setup.engine.rules_sell import evaluate_live_sell_rules
from trade_setup.engine.risk import execute_order_disciplines, execute_sell_order_disciplines
from trade_setup.engine.orders import place_kite_bracket_defense, place_kite_sell_bracket_defense
from trade_setup.engine.auditor import audit_active_trades

class KiteExecutionEngine:
    # Class-level delegate method bindings
    get_orb_range_from_logs = get_orb_range_from_logs
    get_volume_baseline = get_volume_baseline
    get_volume_baseline_15m = get_volume_baseline_15m
    get_tick_spread_volume = get_tick_spread_volume
    get_daily_open_price = get_daily_open_price
    
    fetch_transaction_costs = fetch_transaction_costs
    log_trade_to_journal = log_trade_to_journal
    evaluate_live_rules = evaluate_live_rules
    evaluate_live_sell_rules = evaluate_live_sell_rules
    execute_order_disciplines = execute_order_disciplines
    execute_sell_order_disciplines = execute_sell_order_disciplines
    place_kite_bracket_defense = place_kite_bracket_defense
    place_kite_sell_bracket_defense = place_kite_sell_bracket_defense
    audit_active_trades = audit_active_trades

    def __init__(self, dry_run=True):
        self.dry_run = dry_run
        self.kite = None
        self.active_trades = {}
        self.orb_ranges = {}  # {symbol: {"high": float, "low": float}}
        self.risk_per_trade = 2500.0  # Conservative risk limit per trade (₹)
        self.max_active_trades = 3    # Limit correlation risk
        
        # Stateful File Pointers for ultra-fast incremental reading
        self.file_pointers = {
            config.FYERS_LOG: 0,
            config.FYERS_LOG_5M: 0,
            config.FYERS_LOG_15M: 0,
            config.FYERS_INDICATORS_5M: 0
        }
        self.memory_logs = {
            config.FYERS_LOG: [],
            config.FYERS_LOG_5M: [],
            config.FYERS_LOG_15M: [],
            config.FYERS_INDICATORS_5M: []
        }

    def sync_logs_to_memory(self):
        """Ultra-fast incremental memory load. Reads only new lines from the hard drive."""
        for file_path in self.file_pointers.keys():
            if not os.path.exists(file_path):
                continue
            
            with open(file_path, "r") as f:
                f.seek(self.file_pointers[file_path])
                new_lines = f.readlines()
                self.file_pointers[file_path] = f.tell()
                
                if new_lines:
                    reader = csv.reader(new_lines)
                    for row in reader:
                        if not row or (len(row) > 0 and row[0] == "timestamp"):
                            continue
                        self.memory_logs[file_path].append(row)
                    
                    # Memory cap to prevent RAM bloating
                    if len(self.memory_logs[file_path]) > 25000:
                        self.memory_logs[file_path] = self.memory_logs[file_path][-25000:]
        
        print(f"============================================================")
        print(f"⚡ ZERODHA KITE EXECUTION ENGINE INITIALIZED")
        print(f"🛡️ RISK PARAMETER: ₹{self.risk_per_trade} Per Trade (MIS Mode Only)")
        print(f"🔧 MODE: {'[DRY RUN / SIMULATION MODE]' if self.dry_run else '[LIVE EXECUTION MODE]'}")
        print(f"============================================================")
        
        if not self.dry_run:
            self.init_kite_client()
            self.sync_broker_state()
        else:
            self.completed_trades_today = set()

    def sync_broker_state(self):
        """Syncs the engine state with the live Kite broker to recover from restarts."""
        print("🔄 Syncing state with Zerodha Kite...")
        try:
            # 1. Fetch Today's Orders for Cooldown
            orders = self.kite.orders()
            self.completed_trades_today = set()
            pending_sl_orders = {}
            
            for order in orders:
                sym = order.get("tradingsymbol")
                status = order.get("status")
                order_type = order.get("order_type")
                
                # If there's a complete or rejected order, mark as interacted today
                if status in ["COMPLETE", "REJECTED"]:
                    self.completed_trades_today.add(sym)
                    
                # Track pending SL orders to attach to active trades
                if status == "TRIGGER PENDING" and order_type == "SL":
                    pending_sl_orders[sym] = {
                        "sl_id": order.get("order_id"),
                        "sl_price": float(order.get("trigger_price", 0))
                    }
                    
            # 2. Fetch Active Positions to Reconstruct Memory
            positions = self.kite.positions()
            net_positions = positions.get("net", [])
            
            for pos in net_positions:
                sym = pos.get("tradingsymbol")
                product = pos.get("product")
                qty = pos.get("quantity", 0)
                
                # If we have an open MIS position
                if product == self.kite.PRODUCT_MIS and qty != 0:
                    avg_price = float(pos.get("average_price", 0))
                    direction = "BUY" if qty > 0 else "SELL"
                    
                    # Remove from completed if we currently hold it (it's active, not completed)
                    if sym in self.completed_trades_today:
                        self.completed_trades_today.remove(sym)
                        
                    # Reconstruct active_trades
                    self.active_trades[sym] = {
                        "entry": avg_price,
                        "qty": abs(qty),
                        "direction": direction,
                        "sl": pending_sl_orders.get(sym, {}).get("sl_price", 0.0),
                        "sl_id": pending_sl_orders.get(sym, {}).get("sl_id", None)
                    }
                    print(f"✅ Recovered Active Trade: {direction} {abs(qty)} {sym} @ ₹{avg_price} (SL: ₹{self.active_trades[sym]['sl']})")
                    
            print(f"✅ Broker Sync Complete. Found {len(self.active_trades)} active trades. {len(self.completed_trades_today)} symbols in cooldown.")
        except Exception as e:
            print(f"❌ Failed to sync broker state: {e}")
            self.completed_trades_today = set()

    def init_kite_client(self):
        """Initializes the official KiteConnect client using cached daily session token or environment fallback."""
        try:
            from kiteconnect import KiteConnect
            
            api_key = config.KITE_API_KEY
            access_token = None
            
            # Try loading cached daily token
            if os.path.exists(config.KITE_TOKEN_FILE):
                with open(config.KITE_TOKEN_FILE, "r") as f:
                    try:
                        token_data = json.load(f)
                        access_token = token_data.get("access_token")
                        # Validate that it is from today (after 6 AM IST)
                        token_date_str = token_data.get("date")
                        if token_date_str:
                            from datetime import datetime as dt
                            token_date = dt.strptime(token_date_str, "%Y-%m-%d").date()
                            today = datetime.now().date()
                            if token_date != today and datetime.now().hour >= 6:
                                print("⚠️  Cached Zerodha Kite token expired (needs daily 6:00 AM refresh).")
                                access_token = None
                    except Exception as e:
                        print(f"⚠️ Error parsing cached Kite token: {e}")

            # If no cached token, try environment fallback
            if not access_token:
                access_token = os.getenv("KITE_ACCESS_TOKEN")
            
            if not api_key or not access_token:
                print("⚠️  Warning: No active Zerodha Kite session found.")
                print("👉 Please authorize Kite Connect via the Web Dashboard, or place KITE_ACCESS_TOKEN in .env.")
                print("👉 Falling back to Simulation Mode for safety.")
                self.dry_run = True
                return
                
            self.kite = KiteConnect(api_key=api_key)
            self.kite.set_access_token(access_token)
            
            # Register Session Expiry Hook (Mid-day Token Termination Guard)
            def on_session_expiry():
                print("\n🚨🚨🚨 [CRITICAL ALERT] ZERODHA KITE SESSION EXPIRED MID-DAY! 🚨🚨🚨")
                print("⚠️  Any active orders, modifications, or target checks will now fail.")
                print("🛡️  SAFE GUARD: Forcing engine back to Simulation (Dry-Run) Mode immediately to protect capital!")
                self.dry_run = True
                
            self.kite.set_session_expiry_hook(on_session_expiry)
            print("🟢 Successfully authenticated with Zerodha Kite Connect API using cached daily session.")
        except ImportError:
            print("⚠️  KiteConnect package not installed in this environment.")
            print("👉 Run: ./venv/bin/pip install kiteconnect")
            print("👉 Falling back to Simulation Mode.")
            self.dry_run = True
        except Exception as e:
            print(f"❌ Failed to connect to Kite API: {e}")
            self.dry_run = True

    def load_watchlist(self):
        """Loads your pre-market stock selections from your JSON watchlist."""
        if os.path.exists(config.WATCHLIST_FILE):
            with open(config.WATCHLIST_FILE, 'r') as f:
                data = json.load(f)
                if isinstance(data, list):
                    symbols = data
                elif isinstance(data, dict):
                    symbols = data.get("buy", []) + data.get("sell", [])
                else:
                    symbols = []
                # Parse symbols (e.g. "NSE:BPCL-EQ" -> "BPCL")
                parsed = []
                for s in symbols:
                    if ":" in s:
                        s_ticker = s.split(":")[1].split("-EQ")[0]
                    else:
                        s_ticker = s.split("-EQ")[0]
                    parsed.append(s_ticker)
                return parsed
        return []

    def get_symbol_direction(self, symbol):
        """Returns 'BUY' or 'SELL' for a given symbol by reading the watchlist config."""
        if os.path.exists(config.WATCHLIST_FILE):
            try:
                with open(config.WATCHLIST_FILE, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        for s in data.get("sell", []):
                            ticker = s.split(":")[1].split("-EQ")[0] if ":" in s else s.split("-EQ")[0]
                            if ticker == symbol:
                                return "SELL"
                        for s in data.get("buy", []):
                            ticker = s.split(":")[1].split("-EQ")[0] if ":" in s else s.split("-EQ")[0]
                            if ticker == symbol:
                                return "BUY"
            except Exception as e:
                print(f"⚠️ Error checking symbol direction: {e}")
        return "BUY"

    def run_polling_loop(self):
        """Active scanner that continuously audits watchlist symbols against filters."""
        print("\n📡 Start active scanning. Press Ctrl+C to terminate.")
        try:
            while True:
                try:
                    # Ultra-Fast Memory Sync
                    self.sync_logs_to_memory()
                    
                    # 1. Audit active trades for trailing stop updates and profit booking
                    self.audit_active_trades()

                    # 2. Scan watchlist for new entry triggers
                    watchlist = self.load_watchlist()
                    if not watchlist:
                        print("⚠️ Watchlist is empty. Pre-load your stocks into watchlist.json.")
                        time.sleep(10)
                        continue

                    for symbol in watchlist:
                        if symbol in self.active_trades:
                            continue
                            
                        # COOLDOWN GUARD: Prevent re-entering a stock that was already traded today
                        if hasattr(self, 'completed_trades_today') and symbol in self.completed_trades_today:
                            continue
                        
                        direction = self.get_symbol_direction(symbol)
                        if direction == "SELL":
                            status = self.evaluate_live_sell_rules(symbol)
                            prefix = "[SELL-SCAN]"
                        else:
                            status = self.evaluate_live_rules(symbol)
                            prefix = "[BUY-SCAN]"

                        # Suppress repeating logs to keep execution clear
                        if status and "FAILED" not in str(status):
                            print(f"🔎 {prefix} {symbol}: {status}")
                except Exception as e:
                    print(f"⚠️ Error inside polling loop iteration: {e}")
                
                time.sleep(2.5)  # Poll every 2.5 seconds to minimize disk reading
        except KeyboardInterrupt:
            print("\n👋 Scanning halted by user. Exiting gracefully.")

if __name__ == "__main__":
    # By default, run in safe Simulation mode to protect capital
    # Run with: python3 kite_execution_engine.py live (to connect to your real Zerodha account)
    live_mode = len(sys.argv) > 1 and sys.argv[1].lower() == "live"
    engine = KiteExecutionEngine(dry_run=not live_mode)
    engine.run_polling_loop()
