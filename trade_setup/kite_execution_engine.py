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
from trade_setup.engine.risk import (
    get_today_realized_pnl,
    execute_order_disciplines,
    execute_sell_order_disciplines,
    check_radar_daily_loss_limit,
    execute_radar_buy_disciplines,
    execute_radar_sell_disciplines
)
from trade_setup.engine.orders import place_kite_bracket_defense, place_kite_sell_bracket_defense, round_to_tick
from trade_setup.engine.auditor import audit_active_trades, square_off_radar_position, modify_sl_to_marketable_limit_exit
from trade_setup.engine.rules_pullback import evaluate_pullback_rules

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
    get_today_realized_pnl = get_today_realized_pnl
    execute_order_disciplines = execute_order_disciplines
    execute_sell_order_disciplines = execute_sell_order_disciplines
    place_kite_bracket_defense = place_kite_bracket_defense
    place_kite_sell_bracket_defense = place_kite_sell_bracket_defense
    audit_active_trades = audit_active_trades
    square_off_radar_position = square_off_radar_position
    modify_sl_to_marketable_limit_exit = modify_sl_to_marketable_limit_exit
    evaluate_pullback_rules = evaluate_pullback_rules
    check_radar_daily_loss_limit = check_radar_daily_loss_limit
    execute_radar_buy_disciplines = execute_radar_buy_disciplines
    execute_radar_sell_disciplines = execute_radar_sell_disciplines

    def __init__(self, dry_run=True):
        self.dry_run = dry_run
        self.kite = None
        self.active_trades = {}
        self.orb_ranges = {}  # {symbol: {"high": float, "low": float}}
        self.risk_per_trade = 100.0  # Scaled down for live safety testing (₹)
        self.max_active_trades = 3    # Limit correlation risk
        
        self.trade_attempts = {}      # {symbol: {"attempts": int, "last_exit_time": datetime}}
        self.completed_trades_today = set()
        self.square_off_failures = {}  # {symbol: int} — orphan cleanup counter
        self.max_daily_loss = 500.0    # ₹500 circuit breaker threshold
        self.circuit_breaker_active = False
        self.diagnostics_cache = {}     # Exported to data/engine_state.json for dashboard
        
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
        
        self.initialize_engine()

    def register_trade_exit(self, symbol):
        """Registers a completed trade exit to trigger cooldown and increment attempts."""
        sym = symbol.replace("NSE:", "").replace("-EQ", "").upper()
        now = datetime.now()
        
        if sym not in self.trade_attempts:
            self.trade_attempts[sym] = {"attempts": 0, "last_exit_time": None}
            
        self.trade_attempts[sym]["attempts"] += 1
        self.trade_attempts[sym]["last_exit_time"] = now
        
        # Keep fallback completed_trades_today for backward compatibility
        self.completed_trades_today.add(sym)
        
        print(f"⏱️ [COOLDOWN] Registered exit for {sym}. Total attempts today: {self.trade_attempts[sym]['attempts']}/2. Cooldown active for 30 minutes.")

    def is_cooldown_active(self, symbol):
        """Checks if a symbol is in cooldown or has exhausted its daily entry attempts."""
        sym = symbol.replace("NSE:", "").replace("-EQ", "").upper()
        if sym not in self.trade_attempts:
            return False
            
        stats = self.trade_attempts[sym]
        if stats["attempts"] >= 2:
            return True
            
        if stats["last_exit_time"]:
            elapsed = (datetime.now() - stats["last_exit_time"]).total_seconds()
            if elapsed < 1800:  # 30 minutes in seconds
                return True
                
        return False

    def initialize_engine(self):
        """Runs the one-time startup checks, authenticates with Kite, and syncs initial state."""
        print(f"============================================================")
        print(f"⚡ ZERODHA KITE EXECUTION ENGINE INITIALIZED")
        print(f"🛡️ RISK PARAMETER: ₹{self.risk_per_trade} Per Trade (MIS Mode Only)")
        print(f"🔧 MODE: {'[LIVE EXECUTION MODE]' if not self.dry_run else '[DRY RUN / SIMULATION MODE]'}")
        print(f"============================================================")
        
        if not self.dry_run:
            self.init_kite_client()
            self.sync_broker_state()
        else:
            self.completed_trades_today = set()

    def persist_active_trades(self):
        """Writes active_trades to disk so the dashboard can read real target/SL values."""
        try:
            path = os.path.join("data", "active_trades.json")
            os.makedirs("data", exist_ok=True)
            with open(path, "w") as f:
                json.dump(self.active_trades, f, indent=2)
        except Exception as e:
            print(f"⚠️ Failed to persist active_trades: {e}")

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

    def sync_broker_state(self):
        """Syncs the engine state with the live Kite broker to recover from restarts."""
        print("🔄 Syncing state with Zerodha Kite...")
        
        # Load previously persisted active_trades for target restoration
        persisted_trades = {}
        try:
            persist_path = os.path.join("data", "active_trades.json")
            if os.path.exists(persist_path):
                with open(persist_path, "r") as f:
                    persisted_trades = json.load(f)
        except Exception:
            pass
        
        try:
            # 1. Fetch Today's Orders for Cooldown
            orders = self.kite.orders()
            self.completed_trades_today = set()
            self.trade_attempts = {}
            pending_sl_orders = {}
            
            order_counts = {}
            for order in orders:
                sym = order.get("tradingsymbol")
                status = order.get("status")
                order_type = order.get("order_type")
                
                # Count filled orders to reconstruct attempts
                if status == "COMPLETE":
                    order_counts[sym] = order_counts.get(sym, 0) + 1
                    
                if status in ["COMPLETE", "REJECTED"]:
                    self.completed_trades_today.add(sym)
                    
                # Track pending SL orders to attach to active trades
                if status == "TRIGGER PENDING" and order_type == "SL":
                    pending_sl_orders[sym] = {
                        "sl_id": order.get("order_id"),
                        "sl_price": float(order.get("trigger_price", 0.0)),
                        "quantity": int(order.get("quantity", 0)),
                        "transaction_type": order.get("transaction_type")
                    }
                    
            for sym, count in order_counts.items():
                attempts = count // 2
                if attempts > 0:
                    self.trade_attempts[sym] = {
                        "attempts": attempts,
                        "last_exit_time": datetime.now()  # Assume cooldown is active from restart
                    }
                    if attempts >= 2:
                        self.completed_trades_today.add(sym)
                        
            # 2. Fetch Active Positions to Reconstruct Memory and Reconcile
            positions = self.kite.positions()
            net_positions = positions.get("net", [])
            
            reconciled_symbols = set()
            
            for pos in net_positions:
                sym = pos.get("tradingsymbol")
                product = pos.get("product")
                qty = pos.get("quantity", 0)
                
                # If we have an open MIS position
                if product == self.kite.PRODUCT_MIS and qty != 0:
                    avg_price = float(pos.get("average_price", 0))
                    direction = "BUY" if qty > 0 else "SELL"
                    target_qty = abs(qty)
                    exit_direction = "SELL" if direction == "BUY" else "BUY"
                    
                    # Remove from completed/cooldown if we currently hold it (it's active, not completed)
                    if sym in self.completed_trades_today:
                        self.completed_trades_today.remove(sym)
                    if sym in self.trade_attempts:
                        self.trade_attempts[sym]["attempts"] = max(0, self.trade_attempts[sym]["attempts"] - 1)
                        self.trade_attempts[sym]["last_exit_time"] = None
                    
                    # Restore target and SL from persisted state if available
                    persisted = persisted_trades.get(sym, {})
                    restored_target = persisted.get("target")
                    restored_sl = persisted.get("sl")
                    
                    sl_info = pending_sl_orders.get(sym)
                    sl_id = None
                    sl_price = 0.0
                    
                    if sl_info:
                        sl_id = sl_info["sl_id"]
                        sl_price = sl_info["sl_price"]
                        sl_qty = sl_info["quantity"]
                        sl_tx = sl_info["transaction_type"]
                        
                        # Reconcile quantity or transaction type mismatch
                        if sl_qty != target_qty or sl_tx != exit_direction:
                            if sl_tx != exit_direction:
                                print(f"⚠️ [SELF-HEALING] Pending SL order {sl_id} direction {sl_tx} does not match exit direction {exit_direction}. Canceling...")
                                try:
                                    self.kite.cancel_order(variety=self.kite.VARIETY_REGULAR, order_id=sl_id)
                                except Exception as cancel_err:
                                    print(f"❌ [SELF-HEALING] Failed to cancel mismatched SL: {cancel_err}")
                                sl_id = None
                                sl_price = 0.0
                            else:
                                print(f"⚠️ [SELF-HEALING] Detected mismatched pending SL order {sl_id} quantity for {sym}. Order Qty: {sl_qty}, Position Qty: {target_qty}. Modifying...")
                                try:
                                    self.kite.modify_order(
                                        variety=self.kite.VARIETY_REGULAR,
                                        order_id=sl_id,
                                        quantity=target_qty
                                    )
                                    print(f"✅ [SELF-HEALING] Successfully modified pending SL order {sl_id} quantity to {target_qty}!")
                                except Exception as mod_err:
                                    print(f"❌ [SELF-HEALING] Failed to modify pending SL order {sl_id}: {mod_err}")
                                    
                    if not sl_id:
                        # Check Case A: Missing SL
                        print(f"⚠️ [SELF-HEALING] Open position for {sym} has NO matching pending SL order! Restoring protection...")
                        # 1. Attempt to find SL price from persisted trades
                        if restored_sl and restored_sl > 0:
                            sl_price = restored_sl
                            print(f"👉 Found persisted SL price: ₹{sl_price:.2f}")
                        else:
                            # 2. Safety Fallback: Calculate 1% stop-loss
                            if direction == "BUY":
                                sl_price = round_to_tick(avg_price * 0.99)
                            else:
                                sl_price = round_to_tick(avg_price * 1.01)
                            print(f"👉 Calculated safety fallback SL price (1.0% width): ₹{sl_price:.2f}")
                            
                        # Place new SL order
                        try:
                            sl_id = self.kite.place_order(
                                variety=self.kite.VARIETY_REGULAR,
                                exchange=self.kite.EXCHANGE_NSE,
                                tradingsymbol=sym,
                                transaction_type=exit_direction,
                                quantity=target_qty,
                                product=self.kite.PRODUCT_MIS,
                                order_type=self.kite.ORDER_TYPE_SL,
                                trigger_price=sl_price,
                                price=sl_price
                            )
                            print(f"✅ [SELF-HEALING] Successfully placed missing SL order for {sym}. Order ID: {sl_id}")
                        except Exception as place_err:
                            print(f"❌ [SELF-HEALING] Failed to place safety SL order for {sym}: {place_err}")
                    
                    # Reconstruct active_trades
                    self.active_trades[sym] = {
                        "entry": avg_price,
                        "qty": target_qty,
                        "direction": direction,
                        "sl": sl_price if sl_price > 0.0 else (restored_sl if restored_sl else 0.0),
                        "sl_id": sl_id,
                        "target": restored_target
                    }
                    target_display = f"₹{restored_target}" if restored_target else "unknown"
                    print(f"✅ Recovered Active Trade: {direction} {target_qty} {sym} @ ₹{avg_price} (SL: ₹{self.active_trades[sym]['sl']}, Target: {target_display})")
                    reconciled_symbols.add(sym)
            
            # Check Case B: Orphan Pending SL Orders
            for sym, sl_info in pending_sl_orders.items():
                if sym not in reconciled_symbols:
                    sl_id = sl_info["sl_id"]
                    print(f"⚠️ [SELF-HEALING] Detected orphan pending SL order {sl_id} for {sym} (no open MIS position). Canceling...")
                    try:
                        self.kite.cancel_order(
                            variety=self.kite.VARIETY_REGULAR,
                            order_id=sl_id
                        )
                        print(f"✅ [SELF-HEALING] Successfully cancelled orphan pending SL order {sl_id}!")
                    except Exception as cancel_err:
                        print(f"❌ [SELF-HEALING] Failed to cancel orphan pending SL order {sl_id}: {cancel_err}")
                        
            print(f"✅ Broker Sync & Self-Healing Complete. Found {len(self.active_trades)} active trades. {len(self.trade_attempts)} symbols recorded in attempt logs.")
        except Exception as e:
            print(f"❌ Failed to sync broker state: {e}")
            self.completed_trades_today = set()
            self.trade_attempts = {}

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

    def load_radar_watchlist(self):
        import json
        import os
        path = "data/radar_watchlist.json"
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Error loading radar watchlist: {e}")
            return []

    def save_radar_watchlist(self, data):
        import json
        import os
        path = "data/radar_watchlist.json"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"⚠️ Error saving radar watchlist: {e}")

    def export_diagnostics_state(self):
        """Exports current engine rule evaluation state to data/engine_state.json for the dashboard.
        This is read-only telemetry — zero impact on execution paths."""
        import tempfile
        try:
            now = datetime.now()
            now_time = now.time()
            today_str = now.strftime("%Y-%m-%d")
            state = {
                "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                "mode": "LIVE" if not self.dry_run else "DRY_RUN",
                "circuit_breaker_active": self.circuit_breaker_active,
                "max_daily_loss": self.max_daily_loss,
                "realized_pnl": 0.0,
                "orb_active_count": len([s for s, t in self.active_trades.items() if t.get("strategy", "ORB") == "ORB"]),
                "radar_active_count": len([s for s, t in self.active_trades.items() if t.get("strategy") == "RADAR"]),
                "watchlist_candidates": [],
                "active_positions": [],
                "radar_candidates": []
            }

            # Realized P&L (safe — uses existing method)
            try:
                state["realized_pnl"] = round(self.get_today_realized_pnl(), 2)
            except Exception:
                pass

            # ── Watchlist Candidate Diagnostics ──
            watchlist = self.load_watchlist()
            for symbol in (watchlist or []):
                direction = self.get_symbol_direction(symbol)
                diag = {
                    "symbol": symbol,
                    "direction": direction,
                    "status": "IN_TRADE" if symbol in self.active_trades else "SCANNING",
                    "rules": []
                }

                if symbol in self.active_trades:
                    # Skip rule checks for active trades (they show in active_positions)
                    state["watchlist_candidates"].append(diag)
                    continue

                # Cooldown check
                cooldown = self.is_cooldown_active(symbol)
                diag["rules"].append({"name": "Cooldown Clear", "pass": not cooldown,
                    "detail": "In cooldown" if cooldown else "OK"})
                if cooldown:
                    diag["status"] = "COOLDOWN"
                    state["watchlist_candidates"].append(diag)
                    continue

                # Time window
                market_live = now_time >= datetime.strptime("09:30:00", "%H:%M:%S").time()
                past_cutoff = now_time >= datetime.strptime("15:00:00", "%H:%M:%S").time()
                time_ok = market_live and not past_cutoff
                diag["rules"].append({"name": "Time Window (09:30-15:00)", "pass": time_ok,
                    "detail": f"Current: {now_time.strftime('%H:%M:%S')}"})

                # Active slots
                orb_count = state["orb_active_count"]
                slots_ok = orb_count < 3
                diag["rules"].append({"name": "ORB Slot Available", "pass": slots_ok,
                    "detail": f"Active: {orb_count}/3"})

                # Circuit breaker
                cb_ok = not self.circuit_breaker_active
                diag["rules"].append({"name": "Circuit Breaker OK", "pass": cb_ok,
                    "detail": f"Realized: ₹{state['realized_pnl']} / Max: ₹{self.max_daily_loss}"})

                # Fetch latest indicators for this symbol
                latest_row = None
                for row in self.memory_logs.get(config.FYERS_INDICATORS_5M, []):
                    if len(row) < 11 or not row[0].startswith(today_str):
                        continue
                    sym = row[1]
                    row_ticker = sym.split(":")[1].split("-EQ")[0] if ":" in sym else sym
                    if row_ticker == symbol or sym == symbol:
                        latest_row = row

                if latest_row:
                    try:
                        price = float(latest_row[2])
                        vwap = float(latest_row[7])
                        ema20 = float(latest_row[3])
                        ema50 = float(latest_row[4])
                        ema200 = float(latest_row[5])
                        rsi = float(latest_row[6])

                        diag["price"] = price

                        if direction == "BUY":
                            diag["rules"].append({"name": "VWAP Anchor", "pass": price > vwap,
                                "detail": f"Price: ₹{price:.2f} / VWAP: ₹{vwap:.2f}"})
                            diag["rules"].append({"name": "EMA Alignment", "pass": ema20 > ema50 and price > ema200,
                                "detail": f"EMA20: {ema20:.2f} {'>' if ema20 > ema50 else '<='} EMA50: {ema50:.2f} | Price {'>' if price > ema200 else '<='} EMA200: {ema200:.2f}"})
                            diag["rules"].append({"name": "RSI Momentum (50-70)", "pass": 50 <= rsi <= 70,
                                "detail": f"RSI: {rsi:.1f}"})

                            orb = self.orb_ranges.get(symbol)
                            if orb:
                                orb_high = orb["high"]
                                breakout = price > orb_high
                                pct_away = ((orb_high - price) / orb_high * 100) if not breakout else 0
                                diag["rules"].append({"name": "Breakout Trigger", "pass": breakout,
                                    "detail": f"Price: ₹{price:.2f} / ORB High: ₹{orb_high:.2f}" + (f" ({pct_away:.2f}% away)" if not breakout else "")})
                            else:
                                diag["rules"].append({"name": "ORB Range", "pass": False, "detail": "Not yet locked"})

                        else:  # SELL
                            diag["rules"].append({"name": "VWAP Anchor", "pass": price < vwap,
                                "detail": f"Price: ₹{price:.2f} / VWAP: ₹{vwap:.2f}"})
                            diag["rules"].append({"name": "EMA Alignment", "pass": ema20 < ema50 and price < ema200,
                                "detail": f"EMA20: {ema20:.2f} {'<' if ema20 < ema50 else '>='} EMA50: {ema50:.2f} | Price {'<' if price < ema200 else '>='} EMA200: {ema200:.2f}"})
                            diag["rules"].append({"name": "RSI Momentum (30-50)", "pass": 30 <= rsi <= 50,
                                "detail": f"RSI: {rsi:.1f}"})

                            orb = self.orb_ranges.get(symbol)
                            if orb:
                                orb_low = orb["low"]
                                breakdown = price < orb_low
                                pct_away = ((price - orb_low) / orb_low * 100) if not breakdown else 0
                                diag["rules"].append({"name": "Breakdown Trigger", "pass": breakdown,
                                    "detail": f"Price: ₹{price:.2f} / ORB Low: ₹{orb_low:.2f}" + (f" ({pct_away:.2f}% away)" if not breakdown else "")})
                            else:
                                diag["rules"].append({"name": "ORB Range", "pass": False, "detail": "Not yet locked"})

                        # Tick Spread Skew
                        buy_vol, sell_vol = self.get_tick_spread_volume(symbol)
                        if direction == "BUY" and sell_vol > 0:
                            ratio = buy_vol / sell_vol
                            diag["rules"].append({"name": "Tick Spread Skew (≥1.15)", "pass": ratio >= 1.15,
                                "detail": f"Buyer/Seller: {ratio:.2f}"})
                        elif direction == "SELL" and buy_vol > 0:
                            ratio = sell_vol / buy_vol
                            diag["rules"].append({"name": "Tick Spread Skew (≥1.15)", "pass": ratio >= 1.15,
                                "detail": f"Seller/Buyer: {ratio:.2f}"})

                    except (ValueError, IndexError):
                        pass
                else:
                    diag["rules"].append({"name": "Telemetry Data", "pass": False, "detail": "No indicator rows found"})

                state["watchlist_candidates"].append(diag)

            # ── Active Position Diagnostics ──
            for symbol, trade in self.active_trades.items():
                pos = {
                    "symbol": symbol,
                    "direction": trade.get("direction", "BUY"),
                    "strategy": trade.get("strategy", "ORB"),
                    "entry": trade.get("entry"),
                    "qty": trade.get("qty"),
                    "target": trade.get("target"),
                    "stop_loss": trade.get("stop_loss"),
                    "sl_trailed_to_be": trade.get("sl_trailed_to_be", False),
                    "rules": []
                }
                entry = float(trade.get("entry", 0))
                target = float(trade.get("target", 0))
                sl = float(trade.get("stop_loss", 0))

                # Fetch latest price
                ltp = None
                for row in self.memory_logs.get(config.FYERS_INDICATORS_5M, []):
                    if len(row) < 11 or not row[0].startswith(today_str):
                        continue
                    sym = row[1]
                    row_ticker = sym.split(":")[1].split("-EQ")[0] if ":" in sym else sym
                    if row_ticker == symbol or sym == symbol:
                        try:
                            ltp = float(row[2])
                        except (ValueError, IndexError):
                            pass
                pos["ltp"] = ltp

                if ltp and entry > 0:
                    dir_mult = 1 if pos["direction"] == "BUY" else -1
                    pnl_pct = (ltp - entry) / entry * 100 * dir_mult
                    pos["pnl_pct"] = round(pnl_pct, 2)

                    # Target proximity
                    if target > 0:
                        tgt_dist = abs(target - ltp) / entry * 100
                        pos["rules"].append({"name": "Target Hit", "pass": (ltp >= target if pos["direction"] == "BUY" else ltp <= target),
                            "detail": f"LTP: ₹{ltp:.2f} / Target: ₹{target:.2f} ({tgt_dist:.1f}% away)"})

                    # SL proximity
                    if sl > 0:
                        sl_dist = abs(ltp - sl) / entry * 100
                        pos["rules"].append({"name": "Stop Loss Hit", "pass": False,
                            "detail": f"LTP: ₹{ltp:.2f} / SL: ₹{sl:.2f} ({sl_dist:.1f}% away)"})

                    # Break-even trail
                    pos["rules"].append({"name": "SL Trailed to Break-Even", "pass": bool(trade.get("sl_trailed_to_be")),
                        "detail": "70% ADR condition met" if trade.get("sl_trailed_to_be") else "Pending"})

                    # EOD square-off
                    eod_time = datetime.strptime("15:15:00", "%H:%M:%S").time()
                    pos["rules"].append({"name": "EOD Square-Off", "pass": False,
                        "detail": f"Trigger: 15:15 IST | Now: {now_time.strftime('%H:%M:%S')}"})

                state["active_positions"].append(pos)

            # ── Radar Candidate Diagnostics ──
            radar_wl = self.load_radar_watchlist()
            for item in (radar_wl or []):
                sym = item.get("symbol", "")
                base = sym.replace("NSE:", "").replace("-EQ", "").upper()
                rd = {
                    "symbol": base,
                    "direction": item.get("direction", "BUY"),
                    "state": item.get("state", "WAITING_FOR_PULLBACK"),
                    "spike_price": item.get("spike_price"),
                    "pullback_low": item.get("pullback_low"),
                    "pullback_high": item.get("pullback_high"),
                }
                state["radar_candidates"].append(rd)

            self.diagnostics_cache = state

            # Atomic write using tempfile rename
            out_path = os.path.join("data", "engine_state.json")
            os.makedirs("data", exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir="data", suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as tmp_f:
                    json.dump(state, tmp_f)
                os.replace(tmp_path, out_path)
            except Exception:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise

        except Exception as e:
            # Silent fail — diagnostics must never crash the engine
            pass

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
                    self.persist_active_trades()

                    # 2. Scan watchlist for new entry triggers
                    watchlist = self.load_watchlist()
                    if watchlist:
                        for symbol in watchlist:
                            if symbol in self.active_trades:
                                continue
                                
                            # COOLDOWN GUARD: Prevent re-entering a stock if cooldown is active
                            if self.is_cooldown_active(symbol):
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

                    # 3. Scan Radar Watchlist
                    radar_wl = self.load_radar_watchlist()
                    if radar_wl:
                        is_radar_disabled = self.check_radar_daily_loss_limit()
                        radar_active_count = len([s for s, t in self.active_trades.items() if t.get("strategy") == "RADAR"])
                        
                        radar_updated = False
                        radar_to_remove = []
                        
                        for item in radar_wl:
                            symbol = item["symbol"]
                            ticker = symbol.replace("NSE:", "").replace("-EQ", "").upper()
                            
                            # If already active, remove from watchlist
                            if ticker in self.active_trades or symbol in self.active_trades:
                                radar_to_remove.append(item)
                                continue
                                
                            # If daily loss limit hit or max radar trades hit, do not evaluate trigger
                            if is_radar_disabled or radar_active_count >= 2:
                                continue
                                
                            # If cooldown is active, skip trigger evaluation
                            if self.is_cooldown_active(ticker) or self.is_cooldown_active(symbol):
                                continue
                                
                            status = self.evaluate_pullback_rules(item)
                            
                            if status and "WAITING" not in str(status):
                                print(f"🔎 [RADAR-SCAN] {symbol}: {status}")
                                
                            if status == "INVALIDATED" or "FAILED" in str(status):
                                radar_to_remove.append(item)
                            elif "TRIGGERED" in str(status) or symbol in self.active_trades:
                                radar_to_remove.append(item)
                            else:
                                # Mark as updated to save any progress state (pullback low/high/state)
                                radar_updated = True
                                
                        if radar_to_remove or radar_updated:
                            new_radar_wl = [x for x in radar_wl if x not in radar_to_remove]
                            self.save_radar_watchlist(new_radar_wl)

                    # 4. Export diagnostics state for dashboard (silent, non-blocking)
                    self.export_diagnostics_state()
                            
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
