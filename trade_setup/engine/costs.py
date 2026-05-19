import config

def fetch_transaction_costs(self, symbol, quantity, price, transaction_type):
    """
    Fetches precise transaction costs using Zerodha's get_virtual_contract_note API.
    Falls back to exact mathematical estimates if in dry-run mode or API fails.
    """
    charges = {
        "brokerage": 0.0,
        "stt": 0.0,
        "exchange_charge": 0.0,
        "gst": 0.0,
        "sebi_fee": 0.0,
        "stamp_duty": 0.0,
        "total": 0.0
    }
    
    if self.dry_run or not self.kite:
        # Mathematical Estimation for MIS Intraday (Equity)
        # Brokerage: 0.03% or ₹20 (whichever is lower) per execution
        trade_value = price * quantity
        brokerage = min(trade_value * 0.0003, 20.0)
        
        # STT/CTT: 0.025% on Sell side only for equity MIS
        stt = (trade_value * 0.00025) if transaction_type == "SELL" else 0.0
        
        # Exchange Transaction Charge: NSE: 0.00322% of transaction value
        exchange_charge = trade_value * 0.0000322
        
        # GST: 18% on (Brokerage + Exchange Transaction Charge)
        gst = (brokerage + exchange_charge) * 0.18
        
        # SEBI Turnover Fee: 0.0001% (₹10 / Crore) of transaction value
        sebi_fee = trade_value * 0.000001
        
        # Stamp Duty: 0.003% (₹300 / Crore) on Buy side only
        stamp_duty = (trade_value * 0.00003) if transaction_type == "BUY" else 0.0
        
        total = brokerage + stt + exchange_charge + gst + sebi_fee + stamp_duty
        
        charges = {
            "brokerage": round(brokerage, 2),
            "stt": round(stt, 2),
            "exchange_charge": round(exchange_charge, 2),
            "gst": round(gst, 2),
            "sebi_fee": round(sebi_fee, 2),
            "stamp_duty": round(stamp_duty, 2),
            "total": round(total, 2)
        }
        return charges
        
    try:
        order_param = [{
            "order_id": "dummy_id",
            "exchange": "NSE",
            "tradingsymbol": symbol,
            "transaction_type": transaction_type,
            "variety": "regular",
            "product": "MIS",
            "order_type": "MARKET",
            "quantity": quantity,
            "average_price": price
        }]
        response = self.kite.get_virtual_contract_note(order_param)
        if response and len(response) > 0:
            item_charges = response[0].get("charges", {})
            gst_details = item_charges.get("gst", {})
            charges = {
                "brokerage": float(item_charges.get("brokerage", 0.0)),
                "stt": float(item_charges.get("transaction_tax", 0.0)),
                "exchange_charge": float(item_charges.get("exchange_transaction_charge", 0.0)),
                "gst": float(gst_details.get("total", 0.0)),
                "sebi_fee": float(item_charges.get("sebi_turnover_fee", 0.0)),
                "stamp_duty": float(item_charges.get("stamp_duty", 0.0)),
                "total": float(item_charges.get("total", 0.0))
            }
    except Exception as e:
        print(f"⚠️ Failed to fetch charges via Virtual Contract Note API: {e}. Using mathematical estimation.")
        # Fallback to estimate
        trade_value = price * quantity
        brokerage = min(trade_value * 0.0003, 20.0)
        stt = (trade_value * 0.00025) if transaction_type == "SELL" else 0.0
        exchange_charge = trade_value * 0.0000322
        gst = (brokerage + exchange_charge) * 0.18
        sebi_fee = trade_value * 0.000001
        stamp_duty = (trade_value * 0.00003) if transaction_type == "BUY" else 0.0
        total = brokerage + stt + exchange_charge + gst + sebi_fee + stamp_duty
        charges = {
            "brokerage": round(brokerage, 2),
            "stt": round(stt, 2),
            "exchange_charge": round(exchange_charge, 2),
            "gst": round(gst, 2),
            "sebi_fee": round(sebi_fee, 2),
            "stamp_duty": round(stamp_duty, 2),
            "total": round(total, 2)
        }
    return charges
