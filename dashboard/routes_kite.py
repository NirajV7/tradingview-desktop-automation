from fastapi import APIRouter
from fastapi.responses import JSONResponse

import config
import kite_auth_manager
from dashboard.cache import fyers_cache

router = APIRouter()

@router.get("/api/kite/orders")
async def api_kite_orders():
    orders = kite_auth_manager.get_kite_orders()
    return JSONResponse({"orders": orders})

@router.get("/api/kite/positions")
async def api_kite_positions():
    positions = kite_auth_manager.get_kite_positions()
    orders = kite_auth_manager.get_kite_orders()
    
    enriched_positions = []
    for p in positions:
        symbol = p.get("symbol")
        qty = p.get("quantity", 0)
        avg_price = p.get("average_price", 0.0)

        # Use Kite's native live LTP and PnL — computed server-side by Zerodha
        last_price = p.get("last_price", 0.0)
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
        
        # 2. Get ADR values from Fyers cache
        fyers_sym = None
        for s in fyers_cache.data_5m.keys():
            if symbol in s:
                fyers_sym = s
                break
        
        adr_val = None
        adr_abs_val = None
        today_high = None
        today_low = None
        if fyers_sym:
            ind_5m = fyers_cache.data_5m.get(fyers_sym, [])
            if ind_5m:
                last_ind = ind_5m[-1]
                adr_val = last_ind.get("adr")
                adr_abs_val = last_ind.get("adr_abs")
                today_high = last_ind.get("today_high")
                today_low = last_ind.get("today_low")
        
        # Real-time local adjustment to high/low based on live LTP
        if last_price > 0:
            if today_high is None or last_price > today_high:
                today_high = last_price
            if today_low is None or last_price < today_low:
                today_low = last_price

        # Calculate ADR exhaustion
        adr_exhaustion_pct = 0.0
        today_range = 0.0
        if today_high is not None and today_low is not None and adr_abs_val and adr_abs_val > 0:
            today_range = today_high - today_low
            adr_exhaustion_pct = (today_range / adr_abs_val) * 100.0
        
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
        
        eff_target = target_price
        if not eff_target and adr_abs_val:
            eff_target = avg_price + (adr_abs_val * 1.5) if qty > 0 else avg_price - (adr_abs_val * 1.5)
            
        eff_sl = sl_price
        if not eff_sl and adr_abs_val:
            eff_sl = avg_price - adr_abs_val if qty > 0 else avg_price + adr_abs_val
            
        if target_price and sl_price:
            is_estimated_rr = False
            
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
                if target_price:
                    dist_to_target_pct = ((target_price - last_price) / last_price) * 100.0
                    target_dist_rs = target_price - last_price
                if sl_price:
                    dist_to_sl_pct = ((last_price - sl_price) / last_price) * 100.0
                    sl_dist_rs = last_price - sl_price
            else: # Short
                if target_price:
                    dist_to_target_pct = ((last_price - target_price) / last_price) * 100.0
                    target_dist_rs = last_price - target_price
                if sl_price:
                    dist_to_sl_pct = ((sl_price - last_price) / last_price) * 100.0
                    sl_dist_rs = sl_price - last_price
        
        ghost_oco_active = (target_order_id is not None) and (sl_order_id is not None)
        
        enriched_positions.append({
            "symbol": symbol,
            "quantity": qty,
            "average_price": avg_price,
            "last_price": last_price,
            "pnl": pnl_val,
            "product": p.get("product"),
            "target_price": target_price,
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
async def api_kite_panic():
    res = kite_auth_manager.panic_square_off()
    if res.get("status") == "error":
        return JSONResponse(res, status_code=500)
    elif res.get("status") == "partial":
        return JSONResponse(res, status_code=207)
    return JSONResponse(res)

@router.post("/api/kite/exit_position")
async def api_kite_exit_position(payload: dict):
    symbol = payload.get("symbol")
    if not symbol:
        return JSONResponse({"status": "error", "message": "Symbol is required"}, status_code=400)
    res = kite_auth_manager.exit_single_position(symbol)
    if res.get("status") == "error":
        return JSONResponse(res, status_code=500)
    return JSONResponse(res)

@router.post("/api/kite/scale_out")
async def api_kite_scale_out(payload: dict):
    symbol = payload.get("symbol")
    if not symbol:
        return JSONResponse({"status": "error", "message": "Symbol is required"}, status_code=400)
    res = kite_auth_manager.book_half_position(symbol)
    if res.get("status") == "error":
        return JSONResponse(res, status_code=500)
    return JSONResponse(res)

@router.post("/api/kite/modify_sl")
async def api_kite_modify_sl(payload: dict):
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
