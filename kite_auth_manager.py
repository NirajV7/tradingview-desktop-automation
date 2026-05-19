import os
import json
from datetime import datetime
from kiteconnect import KiteConnect
from config import KITE_TOKEN_FILE, KITE_API_KEY, KITE_API_SECRET, KITE_REDIRECT_URL

def check_kite_auth():
    """Validates local Kite token. Returns (needs_login, auth_url)."""
    def get_new_url():
        return f"https://kite.zerodha.com/connect/login?api_key={KITE_API_KEY}&v=3"

    if not KITE_API_KEY or not KITE_API_SECRET:
        print("⚠️ Missing KITE_API_KEY or KITE_API_SECRET in config/environment.")
        return True, "#"

    if os.path.exists(KITE_TOKEN_FILE):
        with open(KITE_TOKEN_FILE, "r") as f:
            try:
                token_data = json.load(f)
                token_date_str = token_data.get("date")
                if token_date_str:
                    try:
                        from datetime import datetime as dt
                        token_date = dt.strptime(token_date_str, "%Y-%m-%d").date()
                        today = datetime.now().date()
                        # Force daily refresh only if we crossed into a new day AND it is past 6:00 AM IST
                        if token_date != today and datetime.now().hour >= 6:
                            return True, get_new_url()
                    except Exception as e:
                        print(f"Kite date check fallback error: {e}")
                        return True, get_new_url()
                else:
                    return True, get_new_url()
                
                access_token = token_data.get("access_token")
                if not access_token:
                    return True, get_new_url()
                
                return False, None
            except Exception as e:
                print(f"Kite Auth Check Error: {e}")
                return True, get_new_url()
                
    return True, get_new_url()

def exchange_kite_token(request_token):
    """Exchanges a Kite request_token for an access_token and caches it."""
    if not request_token:
        return False, "Request token cannot be empty"
        
    try:
        kite = KiteConnect(api_key=KITE_API_KEY)
        data = kite.generate_session(request_token, api_secret=KITE_API_SECRET)
        access_token = data.get("access_token")
        
        if access_token:
            with open(KITE_TOKEN_FILE, "w") as f:
                json.dump({
                    "access_token": access_token,
                    "date": datetime.now().strftime("%Y-%m-%d")
                }, f)
            return True, "Authorized Kite Connect successfully!"
        return False, "Failed to retrieve access token from session data."
    except Exception as e:
        return False, f"Exception during Kite token exchange: {str(e)}"

def _handle_auth_failure(e):
    """Helper to detect auth failures and clean up token file dynamically."""
    try:
        import kiteconnect.exceptions as ex
        is_auth_err = False
        if isinstance(e, (ex.TokenException, ex.PermissionException)):
            is_auth_err = True
        else:
            err_msg = str(e).lower()
            if "incorrect" in err_msg or "token" in err_msg or "auth" in err_msg or "api_key" in err_msg:
                is_auth_err = True
                
        if is_auth_err:
            print("⚠️ [Kite Auth] Stale or invalid session token detected. Deleting cached token to trigger re-auth.")
            if os.path.exists(KITE_TOKEN_FILE):
                os.remove(KITE_TOKEN_FILE)
    except Exception as helper_err:
        print(f"⚠️ [Kite Auth] Error in auth failure handler: {helper_err}")

def get_kite_margin():

    """Fetches the available equity live balance (buying power). Returns dict or None."""
    if not KITE_API_KEY:
        return None
    if os.path.exists(KITE_TOKEN_FILE):
        with open(KITE_TOKEN_FILE, "r") as f:
            try:
                token_data = json.load(f)
                access_token = token_data.get("access_token")
                if access_token:
                    kite = KiteConnect(api_key=KITE_API_KEY)
                    kite.set_access_token(access_token)
                    margins = kite.margins("equity")
                    
                    net_usable = margins.get("net", 0.0)
                    cash = margins.get("available", {}).get("live_balance", 0.0)
                    collateral = margins.get("available", {}).get("collateral", 0.0)
                    
                    return {
                        "net": f"₹{net_usable:,.2f}",
                        "cash": f"₹{cash:,.2f}",
                        "collateral": f"₹{collateral:,.2f}"
                    }
            except Exception as e:
                print(f"Error fetching Kite margin: {e}")
                _handle_auth_failure(e)
                return None
    return None

def get_kite_orders():
    """Fetches list of live orders from Zerodha Kite."""
    if not KITE_API_KEY:
        return []
    if os.path.exists(KITE_TOKEN_FILE):
        with open(KITE_TOKEN_FILE, "r") as f:
            try:
                token_data = json.load(f)
                access_token = token_data.get("access_token")
                if access_token:
                    kite = KiteConnect(api_key=KITE_API_KEY)
                    kite.set_access_token(access_token)
                    orders = kite.orders()
                    # Return latest orders first (reversed)
                    formatted_orders = []
                    for o in reversed(orders):
                        formatted_orders.append({
                            "order_id": o.get("order_id"),
                            "symbol": o.get("tradingsymbol"),
                            "transaction_type": o.get("transaction_type"),
                            "quantity": o.get("quantity"),
                            "order_type": o.get("order_type"),
                            "status": o.get("status"),
                            "price": o.get("price"),
                            "trigger_price": o.get("trigger_price"),
                            "status_message": o.get("status_message") or ""
                        })
                    return formatted_orders
            except Exception as e:
                print(f"Error fetching Kite orders: {e}")
                _handle_auth_failure(e)
                return []
    return []

def get_kite_positions():
    """Fetches list of active day & net positions from Zerodha Kite."""
    if not KITE_API_KEY:
        return []
    if os.path.exists(KITE_TOKEN_FILE):
        with open(KITE_TOKEN_FILE, "r") as f:
            try:
                token_data = json.load(f)
                access_token = token_data.get("access_token")
                if access_token:
                    kite = KiteConnect(api_key=KITE_API_KEY)
                    kite.set_access_token(access_token)
                    positions = kite.positions()
                    day_positions = positions.get("day", [])
                    
                    formatted_positions = []
                    for p in day_positions:
                        formatted_positions.append({
                            "symbol": p.get("tradingsymbol"),
                            "quantity": p.get("quantity"),
                            "average_price": p.get("average_price"),
                            "last_price": p.get("last_price"),
                            "pnl": p.get("pnl"),
                            "product": p.get("product")
                        })
                    return formatted_positions
            except Exception as e:
                print(f"Error fetching Kite positions: {e}")
                _handle_auth_failure(e)
                return []
    return []

def panic_square_off():
    """Cancels all pending orders and market-closes all active positions on Zerodha Kite."""
    if not KITE_API_KEY:
        return {"status": "error", "message": "API key not configured"}
        
    if not os.path.exists(KITE_TOKEN_FILE):
        return {"status": "error", "message": "No active Kite session"}
        
    with open(KITE_TOKEN_FILE, "r") as f:
        try:
            token_data = json.load(f)
            access_token = token_data.get("access_token")
            if not access_token:
                return {"status": "error", "message": "Access token missing in token file"}
                
            from kiteconnect import KiteConnect
            kite = KiteConnect(api_key=KITE_API_KEY)
            kite.set_access_token(access_token)
            
            summary = {
                "cancelled_orders": 0,
                "squared_positions": 0,
                "errors": []
            }
            
            # 1. Fetch and cancel all open/pending orders
            try:
                orders = kite.orders()
                open_statuses = ["OPEN", "TRIGGER PENDING", "VALIDATION PENDING", "PUT ORDER REQ RECEIVED"]
                for o in orders:
                    if o.get("status") in open_statuses:
                        try:
                            kite.cancel_order(variety=o.get("variety"), order_id=o.get("order_id"))
                            summary["cancelled_orders"] += 1
                        except Exception as e:
                            summary["errors"].append(f"Cancel order {o.get('order_id')} failed: {e}")
            except Exception as e:
                summary["errors"].append(f"Fetch orders failed: {e}")
                
            # 2. Fetch and market-square off all active day positions
            try:
                positions = kite.positions()
                day_positions = positions.get("day", [])
                for p in day_positions:
                    qty = p.get("quantity", 0)
                    if qty != 0:
                        symbol = p.get("tradingsymbol")
                        exchange = p.get("exchange")
                        product = p.get("product")
                        
                        # Determine exit transaction type
                        tx_type = "SELL" if qty > 0 else "BUY"
                        exit_qty = abs(qty)
                        
                        try:
                            # Submit market order to square off
                            kite.place_order(
                                variety="regular",
                                exchange=exchange,
                                tradingsymbol=symbol,
                                transaction_type=tx_type,
                                quantity=exit_qty,
                                product=product,
                                order_type="MARKET"
                            )
                            summary["squared_positions"] += 1
                        except Exception as e:
                            summary["errors"].append(f"Square off {symbol} failed: {e}")
            except Exception as e:
                summary["errors"].append(f"Fetch positions failed: {e}")
                
            if summary["errors"]:
                return {
                    "status": "partial",
                    "message": f"Panic complete with errors. Cancelled: {summary['cancelled_orders']}, Squared: {summary['squared_positions']}",
                    "details": summary
                }
            return {
                "status": "success",
                "message": f"Successfully cancelled {summary['cancelled_orders']} orders and squared off {summary['squared_positions']} positions.",
                "details": summary
            }
            
        except Exception as e:
            return {"status": "error", "message": f"Panic failed: {e}"}

def exit_single_position(symbol):
    """Cancels pending orders for the symbol and market-squares off its active position on Zerodha Kite."""
    if not KITE_API_KEY:
        return {"status": "error", "message": "API key not configured"}
    if not os.path.exists(KITE_TOKEN_FILE):
        return {"status": "error", "message": "No active Kite session"}
        
    with open(KITE_TOKEN_FILE, "r") as f:
        try:
            token_data = json.load(f)
            access_token = token_data.get("access_token")
            if not access_token:
                return {"status": "error", "message": "Access token missing"}
                
            kite = KiteConnect(api_key=KITE_API_KEY)
            kite.set_access_token(access_token)
            
            # 1. Cancel pending orders for this symbol
            cancelled = 0
            try:
                orders = kite.orders()
                open_statuses = ["OPEN", "TRIGGER PENDING", "VALIDATION PENDING", "PUT ORDER REQ RECEIVED"]
                for o in orders:
                    if o.get("tradingsymbol") == symbol and o.get("status") in open_statuses:
                        kite.cancel_order(variety=o.get("variety"), order_id=o.get("order_id"))
                        cancelled += 1
            except Exception as e:
                print(f"Cancel orders for {symbol} failed: {e}")
                
            # 2. Square off day positions for this symbol
            squared = False
            positions = kite.positions()
            day_positions = positions.get("day", [])
            for p in day_positions:
                if p.get("tradingsymbol") == symbol:
                    qty = p.get("quantity", 0)
                    if qty != 0:
                        exchange = p.get("exchange")
                        product = p.get("product")
                        tx_type = "SELL" if qty > 0 else "BUY"
                        exit_qty = abs(qty)
                        
                        kite.place_order(
                            variety="regular",
                            exchange=exchange,
                            tradingsymbol=symbol,
                            transaction_type=tx_type,
                            quantity=exit_qty,
                            product=product,
                            order_type="MARKET"
                        )
                        squared = True
                        break
            
            return {
                "status": "success",
                "message": f"Exit completed for {symbol}. Orders cancelled: {cancelled}, Position squared: {squared}"
            }
        except Exception as e:
            return {"status": "error", "message": f"Exit failed for {symbol}: {e}"}




