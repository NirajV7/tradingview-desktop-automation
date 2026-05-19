def execute_order_disciplines(self, symbol, price, stop_loss):
    """Calculates size, targets, and routes orders to Zerodha Kite."""
    if symbol in self.active_trades:
        return

    if len(self.active_trades) >= self.max_active_trades:
        print(f"⚠️  Execution Skipped for {symbol}: Active trade limit ({self.max_active_trades}) reached.")
        return

    # 1. Position Sizing Mathematics
    sl_width = price - stop_loss
    if sl_width <= 0:
        print(f"❌ Sizing Error: Invalid SL width ({sl_width}) for {symbol}")
        return

    quantity = int(self.risk_per_trade // sl_width)
    if quantity <= 0:
        print(f"❌ Sizing Error: Calculated quantity is 0 for {symbol}")
        return

    # 2. Pre-Flight Margin Availability Guard
    available_margin = 500000.0  # High-fidelity simulation default (₹5 Lakhs total)
    required_margin = (price * quantity) * 0.20  # Estimate: 5x leverage for MIS Intraday

    if not self.dry_run and self.kite:
        try:
            margins = self.kite.margins("equity")
            available_margin = float(margins["net"])  # Net usable balance (cash + collateral)
        except Exception as e:
            print(f"⚠️ Failed to fetch live available margin: {e}")
        
        try:
            order_param = [{
                "exchange": "NSE",
                "tradingsymbol": symbol,
                "transaction_type": "BUY",
                "variety": "regular",
                "product": "MIS",
                "order_type": "LIMIT",
                "price": round(round((price * 1.005) / 0.05) * 0.05, 2),
                "quantity": quantity
            }]
            margin_detail = self.kite.order_margins(order_param)
            required_margin = float(margin_detail[0]["total"])
        except Exception as e:
            print(f"⚠️ Failed to fetch required order margin via Zerodha API: {e}")
            required_margin = (price * quantity) * 0.20  # Fallback to estimated 5x leverage

    if required_margin > available_margin:
        margin_per_share = required_margin / quantity
        max_qty = int(available_margin // margin_per_share)
        print(f"⚠️ [MARGIN GUARD] Required Margin (₹{required_margin:.2f}) exceeds Net Available Margin (₹{available_margin:.2f})!")
        if max_qty >= 1:
            print(f"🛡️ [MARGIN GUARD] Dynamically downsizing quantity from {quantity} to {max_qty} shares...")
            quantity = max_qty
            required_margin = max_qty * margin_per_share
        else:
            print(f"🛑 [MARGIN GUARD] Available margin is too low to trade even 1 share (Required per share: ₹{margin_per_share:.2f}). Halting entry gracefully!")
            return
    else:
        print(f"🛡️ [MARGIN GUARD] Pre-Flight Check Passed | Required Margin: ₹{required_margin:.2f} | Net Available Margin: ₹{available_margin:.2f}")

    # 3. Minimum Target placement (1:2 Risk to Reward)
    target = price + (sl_width * 2)

    print(f"\n🚀 >>> BUY TRIGGER DETECTED FOR {symbol} <<< 🚀")
    print(f"💵 Price: ₹{price:.2f} | 🛡️ SL Price: ₹{stop_loss:.2f} (SL Width: ₹{sl_width:.2f})")
    print(f"📊 Sizing: Quantity to execute = {quantity} shares (Max Risk: ₹{self.risk_per_trade})")
    print(f"🎯 Profit Target: ₹{target:.2f} (1:2 R:R Ratio)")

    # 3. Route Orders to Zerodha Kite
    if self.dry_run:
        print(f"   [Simulation Log] Place Order: BUY {quantity} shares of {symbol} (MIS Mode) at Market Price")
        print(f"   [Simulation Log] Place Stop Loss Limit Order (SL): SELL {quantity} shares at Trigger: ₹{stop_loss:.2f}, Price: ₹{stop_loss:.2f}")
        self.active_trades[symbol] = {
            "entry": price,
            "sl": stop_loss,
            "target": target,
            "qty": quantity,
            "status": "SIMULATED"
        }
    else:
        self.place_kite_bracket_defense(symbol, quantity, price, stop_loss, target)
