from fastapi import APIRouter
from fastapi.responses import JSONResponse
import json
import os
from datetime import datetime

import config
import kite_auth_manager
from dashboard.cache import fyers_cache

router = APIRouter()

def _load_engine_active_trades():
    """Reads the engine's persisted active_trades.json for real target/SL values."""
    path = os.path.join("data", "active_trades.json")
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _get_live_ltp_from_log(symbols: list) -> dict:
    """Reads the last known LTP for each symbol from the high-frequency fyers_log CSV.
    This file is updated every ~5s by the Fyers WebSocket logger — zero Zerodha API calls needed.
    Returns: {short_symbol: last_price}
    """
    result = {}
    try:
        log_path = config.FYERS_LOG
        if not os.path.exists(log_path) or os.stat(log_path).st_size == 0:
            return result
        # Read the tail of the file (last 50KB) to avoid loading the whole file
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            file_size = f.tell()
            f.seek(max(0, file_size - 51200))
            tail_bytes = f.read()
        lines = tail_bytes.decode("utf-8", errors="ignore").splitlines()
        # Walk lines in reverse to get last entry per symbol
        seen = set()
        for line in reversed(lines):
            parts = line.split(",")
            if len(parts) < 3:
                continue
            raw_sym = parts[1].strip()
            # Normalize: "NSE:LATENTVIEW-EQ" -> "LATENTVIEW"
            short = raw_sym.split(":")[-1].replace("-EQ", "").replace("-BE", "")
            if short in seen:
                continue
            if short in symbols:
                try:
                    result[short] = float(parts[2].strip())
                    seen.add(short)
                except ValueError:
                    pass
            if len(seen) == len(symbols):
                break
    except Exception as e:
        print(f"⚠️ _get_live_ltp_from_log error: {e}")
    return result

import time as _time

# In-memory cache for intraday high/low — rescan full log every 10s max
_hl_cache = {}
_hl_cache_time = 0.0
_HL_CACHE_TTL = 10.0  # seconds

# Persistent tracker to prevent daily high/low from shrinking/contracting during a trading session
_session_highs = {}
_session_lows = {}
_session_date = None

def _get_persistent_high_low(symbol: str, baseline_high: float, baseline_low: float, ltp: float) -> tuple:
    global _session_highs, _session_lows, _session_date
    today = datetime.now().date()
    if _session_date != today:
        _session_highs.clear()
        _session_lows.clear()
        _session_date = today

    h = baseline_high
    l = baseline_low

    # Ensure we don't drop below session maximums/minimums
    if symbol in _session_highs:
        h = max(h, _session_highs[symbol]) if h is not None else _session_highs[symbol]
    if symbol in _session_lows:
        l = min(l, _session_lows[symbol]) if l is not None else _session_lows[symbol]

    # Update with current LTP
    if ltp > 0:
        h = max(h, ltp) if h is not None else ltp
        l = min(l, ltp) if l is not None else ltp

    # Store back
    if h is not None:
        _session_highs[symbol] = h
    if l is not None:
        _session_lows[symbol] = l

    return h, l

def _get_intraday_high_low_from_log(symbols: list) -> dict:
    """Scans today's Fyers WebSocket log for actual intraday high/low per symbol.
    Results are cached for 10s to avoid re-reading the full file on every 1.5s position poll.
    Returns: {short_symbol: {"high": float, "low": float}}
    """
    global _hl_cache, _hl_cache_time
    now = _time.time()
    if (now - _hl_cache_time) < _HL_CACHE_TTL and _hl_cache:
        # Return cached result, filtered to requested symbols
        return {s: _hl_cache[s] for s in symbols if s in _hl_cache}
    
    result = {}
    try:
        log_path = config.FYERS_LOG
        if not os.path.exists(log_path) or os.stat(log_path).st_size == 0:
            return result
        today_prefix = datetime.now().strftime("%Y-%m-%d")
        # Scan for ALL symbols (not just requested) so cache is reusable
        highs = {}
        lows = {}
        with open(log_path, "r", errors="ignore") as f:
            for line in f:
                if not line.startswith(today_prefix):
                    continue
                parts = line.split(",")
                if len(parts) < 3:
                    continue
                raw_sym = parts[1].strip()
                short = raw_sym.split(":")[-1].replace("-EQ", "").replace("-BE", "")
                try:
                    price = float(parts[2].strip())
                except ValueError:
                    continue
                if price <= 0:
                    continue
                if short not in highs or price > highs[short]:
                    highs[short] = price
                if short not in lows or price < lows[short]:
                    lows[short] = price
        for sym in highs:
            if sym in lows:
                result[sym] = {"high": highs[sym], "low": lows[sym]}
        _hl_cache = result
        _hl_cache_time = now
    except Exception as e:
        print(f"⚠️ _get_intraday_high_low_from_log error: {e}")
    return {s: result[s] for s in symbols if s in result}

def _get_adr_metrics(symbol: str, ltp: float, log_high_low: dict = None) -> dict:
    """Calculates dynamic ADR range exhaustion using persistent high/low and history."""
    fyers_sym = None
    for s in fyers_cache.data_5m.keys():
        # Exact match: "NSE:RELIANCE-EQ" -> "RELIANCE"
        base_symbol = s.split(":")[-1].replace("-EQ", "").replace("-BE", "").upper()
        if base_symbol == symbol.upper():
            fyers_sym = s
            break

    adr_val = 0.0
    adr_abs_val = 0.0
    today_high = None
    today_low = None

    if fyers_sym:
        ind_5m = fyers_cache.data_5m.get(fyers_sym, [])
        if ind_5m:
            last_ind = ind_5m[-1]
            adr_val = last_ind.get("adr", 0.0)
            adr_abs_val = last_ind.get("adr_abs", 0.0)
            today_high = last_ind.get("today_high")
            today_low = last_ind.get("today_low")

    # Blend with Fyers log high/low scan
    hl = log_high_low.get(symbol) if log_high_low else None
    if hl:
        log_h = hl.get("high")
        log_l = hl.get("low")
        if log_h is not None:
            today_high = max(today_high, log_h) if today_high is not None else log_h
        if log_l is not None:
            today_low = min(today_low, log_l) if today_low is not None else log_l

    # Apply persistent session maximums and current live price
    today_high, today_low = _get_persistent_high_low(symbol, today_high, today_low, ltp)

    today_range = 0.0
    adr_exhaustion_pct = 0.0
    if today_high is not None and today_low is not None and adr_abs_val and adr_abs_val > 0:
        today_range = today_high - today_low
        adr_exhaustion_pct = (today_range / adr_abs_val) * 100.0

    return {
        "adr": adr_val,
        "adr_abs": adr_abs_val,
        "today_high": today_high,
        "today_low": today_low,
        "today_range": today_range,
        "adr_exhaustion_pct": adr_exhaustion_pct
    }

@router.get("/api/kite/ltp")
def api_kite_ltp():
    """Ultra-fast LTP + PnL endpoint. Uses Fyers log (no Zerodha API). Call every 500ms."""
    positions = kite_auth_manager.get_kite_positions()
    active = [p for p in positions if p.get("quantity", 0) != 0]
    if not active:
        return JSONResponse({"ticks": []})

    symbols = [p["symbol"] for p in active]
    live_ltp = _get_live_ltp_from_log(symbols)
    fyers_hl = _get_intraday_high_low_from_log(symbols)

    ticks = []
    for p in active:
        sym = p["symbol"]
        qty = p["quantity"]
        avg = p.get("average_price", 0.0)
        ltp = live_ltp.get(sym, p.get("last_price", avg))
        pnl = (ltp - avg) * qty if qty > 0 else (avg - ltp) * abs(qty)
        
        # Pull live ADR metrics for the tick
        adr_metrics = _get_adr_metrics(sym, ltp, fyers_hl)
        
        ticks.append({
            "symbol": sym,
            "ltp": round(ltp, 2),
            "pnl": round(pnl, 2),
            "adr": round(adr_metrics["adr"], 2) if adr_metrics["adr"] else 0.0,
            "adr_abs": round(adr_metrics["adr_abs"], 2) if adr_metrics["adr_abs"] else 0.0,
            "today_range": round(adr_metrics["today_range"], 2),
            "adr_exhaustion_pct": round(adr_metrics["adr_exhaustion_pct"], 2)
        })

    return JSONResponse({"ticks": ticks})



@router.get("/api/kite/orders")
def api_kite_orders():
    orders = kite_auth_manager.get_kite_orders()
    return JSONResponse({"orders": orders})

@router.get("/api/kite/positions")
def api_kite_positions():
    positions = kite_auth_manager.get_kite_positions()
    orders = kite_auth_manager.get_kite_orders()
    
    enriched_positions = []
    engine_trades = _load_engine_active_trades()
    
    # Pre-fetch live Fyers LTP + intraday H/L for all active symbols
    active_symbols = [p.get("symbol") for p in positions if p.get("quantity", 0) != 0]
    fyers_ltp = _get_live_ltp_from_log(active_symbols) if active_symbols else {}
    fyers_hl = _get_intraday_high_low_from_log(active_symbols) if active_symbols else {}
    
    for p in positions:
        symbol = p.get("symbol")
        qty = p.get("quantity", 0)
        avg_price = p.get("average_price", 0.0)

        # Pull real target & SL from engine's persisted state first
        engine_trade = engine_trades.get(symbol, {})
        engine_target = engine_trade.get("target")
        engine_sl = engine_trade.get("sl")

        # Use Fyers WebSocket LTP as primary source (5s fresh), fall back to Kite's cached LTP
        last_price = fyers_ltp.get(symbol, p.get("last_price", 0.0))
        # Compute PnL from live LTP — not Kite's stale pnl field
        if qty != 0 and last_price > 0:
            pnl_val = (last_price - avg_price) * qty if qty > 0 else (avg_price - last_price) * abs(qty)
        else:
            pnl_val = p.get("pnl", 0.0)
        
        # 1. Match active orders for target and SL
        target_price = None
        target_order_id = None
        target_status = None
        target_order_type = None
        
        sl_price = None
        sl_order_id = None
        sl_status = None
        sl_order_type = None
        
        expected_tx = "SELL" if qty > 0 else "BUY"
        
        for o in orders:
            if o.get("symbol") == symbol and o.get("status") in ["OPEN", "TRIGGER PENDING"]:
                if o.get("transaction_type") == expected_tx:
                    otype = o.get("order_type")
                    if otype == "LIMIT":
                        target_price = o.get("price")
                        target_order_id = o.get("order_id")
                        target_status = o.get("status")
                        target_order_type = otype
                    elif otype in ["SL", "SL-M"]:
                        sl_price = o.get("trigger_price") or o.get("price")
                        sl_order_id = o.get("order_id")
                        sl_status = o.get("status")
                        sl_order_type = otype
        
        # 2. Get ADR metrics using dynamic helper
        adr_metrics = _get_adr_metrics(symbol, last_price, fyers_hl)
        adr_val = adr_metrics["adr"]
        adr_abs_val = adr_metrics["adr_abs"]
        today_high = adr_metrics["today_high"]
        today_low = adr_metrics["today_low"]
        today_range = adr_metrics["today_range"]
        adr_exhaustion_pct = adr_metrics["adr_exhaustion_pct"]
        
        
        # 3. Calculate Risk Allocated & Risk %
        allocated_risk = 0.0
        risk_pct = 0.0
        
        if qty != 0:
            effective_sl = sl_price
            if not effective_sl and adr_abs_val:
                effective_sl = avg_price - adr_abs_val if qty > 0 else avg_price + adr_abs_val
            
            if effective_sl:
                allocated_risk = abs(qty * (avg_price - effective_sl))
                # Base on maximum ₹2,500 absolute risk limit
                risk_pct = min(100.0, (allocated_risk / 2500.0) * 100.0)
        
        # 4. Calculate Risk-Reward Ratio (R:R) & Distances
        rr_ratio = 0.0
        is_estimated_rr = True
        
        # Use engine's real target if available, else fall back to ADR estimate
        eff_target = target_price  # from Zerodha LIMIT order (if placed)
        if not eff_target and engine_target:
            eff_target = float(engine_target)
        elif not eff_target and adr_abs_val and qty != 0:
            eff_target = avg_price + (adr_abs_val * 1.5) if qty > 0 else avg_price - (adr_abs_val * 1.5)

        # Use engine's real SL if available, else fall back to ADR estimate
        eff_sl = sl_price  # from Zerodha SL order
        if not eff_sl and engine_sl:
            eff_sl = float(engine_sl)
        elif not eff_sl and adr_abs_val and qty != 0:
            eff_sl = avg_price - adr_abs_val if qty > 0 else avg_price + adr_abs_val
            
        if target_price and sl_price:
            is_estimated_rr = False
        elif engine_target and (sl_price or engine_sl):
            is_estimated_rr = False  # Engine values are real, not estimated
            
        reward_dist = abs(eff_target - avg_price) if eff_target else 0.0
        risk_dist = abs(avg_price - eff_sl) if eff_sl else 0.0
        
        if risk_dist > 0:
            rr_ratio = reward_dist / risk_dist
        dist_to_target_pct = None
        dist_to_sl_pct = None
        target_dist_rs = None
        sl_dist_rs = None
        
        if qty != 0 and last_price > 0:
            if qty > 0: # Long
                if eff_target:
                    dist_to_target_pct = ((eff_target - last_price) / last_price) * 100.0
                    target_dist_rs = eff_target - last_price
                if eff_sl:
                    dist_to_sl_pct = ((last_price - eff_sl) / last_price) * 100.0
                    sl_dist_rs = last_price - eff_sl
            else: # Short
                if eff_target:
                    dist_to_target_pct = ((last_price - eff_target) / last_price) * 100.0
                    target_dist_rs = last_price - eff_target
                if eff_sl:
                    dist_to_sl_pct = ((eff_sl - last_price) / last_price) * 100.0
                    sl_dist_rs = eff_sl - last_price
        
        ghost_oco_active = (target_order_id is not None) and (sl_order_id is not None)
        
        enriched_positions.append({
            "symbol": symbol,
            "quantity": qty,
            "average_price": avg_price,
            "last_price": last_price,
            "pnl": pnl_val,
            "product": p.get("product"),
            "target_price": target_price,           # Zerodha LIMIT order price (if exists)
            "engine_target": eff_target,              # Real engine target (shown in UI)
            "engine_sl": eff_sl,                      # Real engine SL (fallback if no Zerodha order)
            "target_order_id": target_order_id,
            "target_status": target_status,
            "target_order_type": target_order_type,
            "sl_price": sl_price,
            "sl_order_id": sl_order_id,
            "sl_status": sl_status,
            "sl_order_type": sl_order_type,
            "ghost_oco_active": ghost_oco_active,
            "adr": adr_val,
            "adr_abs": adr_abs_val,
            "today_high": today_high,
            "today_low": today_low,
            "today_range": today_range,
            "adr_exhaustion_pct": round(adr_exhaustion_pct, 2),
            "allocated_risk": round(allocated_risk, 2),
            "risk_pct": round(risk_pct, 1),
            "rr_ratio": round(rr_ratio, 2),
            "is_estimated_rr": is_estimated_rr,
            "dist_to_target_pct": round(dist_to_target_pct, 2) if dist_to_target_pct is not None else None,
            "dist_to_sl_pct": round(dist_to_sl_pct, 2) if dist_to_sl_pct is not None else None,
            "target_dist_rs": round(target_dist_rs, 2) if target_dist_rs is not None else None,
            "sl_dist_rs": round(sl_dist_rs, 2) if sl_dist_rs is not None else None,
            "buy_quantity": p.get("buy_quantity", 0),
            "sell_quantity": p.get("sell_quantity", 0),
            "buy_price": p.get("buy_price", 0.0),
            "sell_price": p.get("sell_price", 0.0)
        })
        
    return JSONResponse({"positions": enriched_positions})

@router.post("/api/kite/panic")
def api_kite_panic():
    res = kite_auth_manager.panic_square_off()
    # Force cache refresh immediately to reflect squared off positions on the dashboard
    kite_auth_manager.get_kite_positions(force=True)
    if res.get("status") == "error":
        return JSONResponse(res, status_code=500)
    elif res.get("status") == "partial":
        return JSONResponse(res, status_code=207)
    return JSONResponse(res)

@router.post("/api/kite/exit_position")
def api_kite_exit_position(payload: dict):
    symbol = payload.get("symbol")
    if not symbol:
        return JSONResponse({"status": "error", "message": "Symbol is required"}, status_code=400)
    res = kite_auth_manager.exit_single_position(symbol)
    # Force cache refresh immediately
    kite_auth_manager.get_kite_positions(force=True)
    if res.get("status") == "error":
        return JSONResponse(res, status_code=500)
    return JSONResponse(res)

@router.post("/api/kite/scale_out")
def api_kite_scale_out(payload: dict):
    symbol = payload.get("symbol")
    if not symbol:
        return JSONResponse({"status": "error", "message": "Symbol is required"}, status_code=400)
    res = kite_auth_manager.book_half_position(symbol)
    # Force cache refresh immediately
    kite_auth_manager.get_kite_positions(force=True)
    if res.get("status") == "error":
        return JSONResponse(res, status_code=500)
    return JSONResponse(res)

@router.post("/api/kite/modify_sl")
def api_kite_modify_sl(payload: dict):
    symbol = payload.get("symbol")
    new_sl = payload.get("new_sl_price")
    sl_order_id = payload.get("sl_order_id")
    quantity = payload.get("quantity")
    transaction_type = payload.get("transaction_type")
    product = payload.get("product")
    
    if not symbol or new_sl is None:
        return JSONResponse({"status": "error", "message": "symbol and new_sl_price are required"}, status_code=400)
    
    res = kite_auth_manager.modify_or_place_sl(
        symbol=symbol,
        new_trigger_price=float(new_sl),
        sl_order_id=sl_order_id,
        quantity=quantity,
        transaction_type=transaction_type,
        product=product
    )
    if res.get("status") == "error":
        return JSONResponse(res, status_code=500)
    return JSONResponse(res)
