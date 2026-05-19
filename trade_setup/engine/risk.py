def execute_order_disciplines(self, symbol, price, stop_loss):
    """Calculates size, targets, and routes orders to Zerodha Kite."""
    if symbol in self.active_trades:
        return

    orb_active_count = len([s for s, t in self.active_trades.items() if t.get("strategy", "ORB") == "ORB"])
    if orb_active_count >= 3:
        print(f"⚠️  Execution Skipped for {symbol}: Active ORB trade limit (3) reached.")
        return

    # 1. Position Sizing Mathematics
    sl_width = price - stop_loss
    if sl_width <= 0:
        print(f"❌ Sizing Error: Invalid SL width ({sl_width}) for {symbol}")
        return

    quantity = int(self.risk_per_trade // sl_width)
    quantity = max(1, quantity)

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
            "direction": "BUY",
            "status": "SIMULATED"
        }
    else:
        self.place_kite_bracket_defense(symbol, quantity, price, stop_loss, target)


def execute_sell_order_disciplines(self, symbol, price, stop_loss):
    """Calculates size, targets, and routes sell/short orders to Zerodha Kite."""
    if symbol in self.active_trades:
        return

    orb_active_count = len([s for s, t in self.active_trades.items() if t.get("strategy", "ORB") == "ORB"])
    if orb_active_count >= 3:
        print(f"⚠️  Execution Skipped for {symbol}: Active ORB trade limit (3) reached.")
        return

    # 1. Position Sizing Mathematics (Stop loss is ABOVE entry price for shorts)
    sl_width = stop_loss - price
    if sl_width <= 0:
        print(f"❌ Sizing Error: Invalid SL width ({sl_width}) for short {symbol}")
        return

    quantity = int(self.risk_per_trade // sl_width)
    quantity = max(1, quantity)

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
                "transaction_type": "SELL",
                "variety": "regular",
                "product": "MIS",
                "order_type": "LIMIT",
                "price": round(round((price * 0.995) / 0.05) * 0.05, 2),
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

    # 3. Minimum Target placement (1:2 Risk to Reward for Short)
    target = price - (sl_width * 2)

    print(f"\n🚀 >>> SELL TRIGGER DETECTED FOR {symbol} <<< 🚀")
    print(f"💵 Price: ₹{price:.2f} | 🛡️ SL Price: ₹{stop_loss:.2f} (SL Width: ₹{sl_width:.2f})")
    print(f"📊 Sizing: Quantity to execute = {quantity} shares (Max Risk: ₹{self.risk_per_trade})")
    print(f"🎯 Profit Target: ₹{target:.2f} (1:2 R:R Ratio)")

    # 3. Route Orders to Zerodha Kite
    if self.dry_run:
        print(f"   [Simulation Log] Place Order: SELL {quantity} shares of {symbol} (MIS Mode) at Market Price")
        print(f"   [Simulation Log] Place Stop Loss Limit Order (SL): BUY {quantity} shares at Trigger: ₹{stop_loss:.2f}, Price: ₹{stop_loss:.2f}")
        self.active_trades[symbol] = {
            "entry": price,
            "sl": stop_loss,
            "target": target,
            "qty": quantity,
            "direction": "SELL",
            "status": "SIMULATED"
        }
    else:
        self.place_kite_sell_bracket_defense(symbol, quantity, price, stop_loss, target)


def check_radar_daily_loss_limit(self):
    import csv
    import os
    from datetime import datetime
    import config
    csv_path = config.TRADE_JOURNAL_CSV
    if not os.path.exists(csv_path):
        return False
        
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = row.get("timestamp", "")
                if ts.startswith(today_str):
                    exit_reason = row.get("exit_reason", "")
                    if "(RADAR)" in exit_reason:
                        net_pnl = float(row.get("net_pnl", 0.0))
                        if net_pnl <= -100.0:
                            return True
    except Exception as e:
        print(f"⚠️ Error checking radar daily loss limit: {e}")
    return False


def execute_radar_buy_disciplines(self, symbol, price, pullback_low, orb_high):
    """Calculates size, targets, and routes orders for Radar pullback buy trades."""
    if symbol in self.active_trades:
        return

    # Check daily loss guard
    if self.check_radar_daily_loss_limit():
        print(f"🛑 [RADAR GUARD] Execution Skipped for {symbol}: Radar Daily Max Loss limit reached today.")
        return

    # Check Radar strategy limit (max 2 active radar trades)
    radar_active_count = len([s for s, t in self.active_trades.items() if t.get("strategy") == "RADAR"])
    if radar_active_count >= 2:
        print(f"⚠️  Execution Skipped for {symbol}: Active Radar trade limit (2) reached.")
        return

    # Sizing floor check (SL width floor at 0.25% of entry price)
    raw_sl_width = price - pullback_low
    sl_width = max(raw_sl_width, price * 0.0025)
    stop_loss = price - sl_width

    # Risk allocation is dynamically set via self.risk_per_trade (₹100 for testing, ₹2500 for production)
    quantity = int(self.risk_per_trade // sl_width)
    quantity = max(1, quantity)

    # Margin check
    available_margin = 500000.0
    required_margin = (price * quantity) * 0.20
    if not self.dry_run and self.kite:
        try:
            margins = self.kite.margins("equity")
            available_margin = float(margins["net"])
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
            print(f"⚠️ Failed to fetch required order margin: {e}")
            required_margin = (price * quantity) * 0.20

    if required_margin > available_margin:
        margin_per_share = required_margin / quantity
        max_qty = int(available_margin // margin_per_share)
        print(f"⚠️ [MARGIN GUARD] Required Margin (₹{required_margin:.2f}) exceeds Net Available Margin (₹{available_margin:.2f})!")
        if max_qty >= 1:
            print(f"🛡️ [MARGIN GUARD] Dynamically downsizing quantity from {quantity} to {max_qty} shares...")
            quantity = max_qty
            required_margin = max_qty * margin_per_share
        else:
            print(f"🛑 [MARGIN GUARD] Available margin is too low. Halting entry gracefully!")
            return

    target = price + (sl_width * 2)

    print(f"\n🚀 >>> RADAR BUY TRIGGER DETECTED FOR {symbol} <<< 🚀")
    print(f"💵 Entry: ₹{price:.2f} | 🛡️ Stop Loss: ₹{stop_loss:.2f} (SL Width: ₹{sl_width:.2f})")
    print(f"📊 Sizing: Quantity = {quantity} shares (Max Risk: ₹2500)")
    print(f"🎯 Profit Target: ₹{target:.2f} (1:2 R:R)")

    if self.dry_run:
        print(f"   [Simulation Log] Place Radar Order: BUY {quantity} shares of {symbol} (MIS) at Market Price")
        print(f"   [Simulation Log] Place Radar SL Order: SELL {quantity} shares at Trigger: ₹{stop_loss:.2f}")
        self.active_trades[symbol] = {
            "entry": price,
            "sl": stop_loss,
            "target": target,
            "qty": quantity,
            "direction": "BUY",
            "status": "SIMULATED",
            "strategy": "RADAR"
        }
    else:
        # Route live order
        self.place_kite_bracket_defense(symbol, quantity, price, stop_loss, target)
        if symbol in self.active_trades:
            self.active_trades[symbol]["strategy"] = "RADAR"


def execute_radar_sell_disciplines(self, symbol, price, pullback_high, orb_low):
    """Calculates size, targets, and routes orders for Radar pullback sell (short) trades."""
    if symbol in self.active_trades:
        return

    # Check daily loss guard
    if self.check_radar_daily_loss_limit():
        print(f"🛑 [RADAR GUARD] Execution Skipped for {symbol}: Radar Daily Max Loss limit reached today.")
        return

    # Check Radar strategy limit (max 2 active radar trades)
    radar_active_count = len([s for s, t in self.active_trades.items() if t.get("strategy") == "RADAR"])
    if radar_active_count >= 2:
        print(f"⚠️  Execution Skipped for {symbol}: Active Radar trade limit (2) reached.")
        return

    # Sizing floor check (SL width floor at 0.25% of entry price)
    raw_sl_width = pullback_high - price
    sl_width = max(raw_sl_width, price * 0.0025)
    stop_loss = price + sl_width

    # Risk allocation is dynamically set via self.risk_per_trade (₹100 for testing, ₹2500 for production)
    quantity = int(self.risk_per_trade // sl_width)
    quantity = max(1, quantity)

    # Margin check
    available_margin = 500000.0
    required_margin = (price * quantity) * 0.20
    if not self.dry_run and self.kite:
        try:
            margins = self.kite.margins("equity")
            available_margin = float(margins["net"])
        except Exception as e:
            print(f"⚠️ Failed to fetch live available margin: {e}")
        
        try:
            order_param = [{
                "exchange": "NSE",
                "tradingsymbol": symbol,
                "transaction_type": "SELL",
                "variety": "regular",
                "product": "MIS",
                "order_type": "LIMIT",
                "price": round(round((price * 0.995) / 0.05) * 0.05, 2),
                "quantity": quantity
            }]
            margin_detail = self.kite.order_margins(order_param)
            required_margin = float(margin_detail[0]["total"])
        except Exception as e:
            print(f"⚠️ Failed to fetch required order margin: {e}")
            required_margin = (price * quantity) * 0.20

    if required_margin > available_margin:
        margin_per_share = required_margin / quantity
        max_qty = int(available_margin // margin_per_share)
        print(f"⚠️ [MARGIN GUARD] Required Margin (₹{required_margin:.2f}) exceeds Net Available Margin (₹{available_margin:.2f})!")
        if max_qty >= 1:
            print(f"🛡️ [MARGIN GUARD] Dynamically downsizing quantity from {quantity} to {max_qty} shares...")
            quantity = max_qty
            required_margin = max_qty * margin_per_share
        else:
            print(f"🛑 [MARGIN GUARD] Available margin is too low. Halting entry gracefully!")
            return

    target = price - (sl_width * 2)

    print(f"\n🚀 >>> RADAR SELL TRIGGER DETECTED FOR {symbol} <<< 🚀")
    print(f"💵 Entry: ₹{price:.2f} | 🛡️ Stop Loss: ₹{stop_loss:.2f} (SL Width: ₹{sl_width:.2f})")
    print(f"📊 Sizing: Quantity = {quantity} shares (Max Risk: ₹2500)")
    print(f"🎯 Profit Target: ₹{target:.2f} (1:2 R:R)")

    if self.dry_run:
        print(f"   [Simulation Log] Place Radar Order: SELL {quantity} shares of {symbol} (MIS) at Market Price")
        print(f"   [Simulation Log] Place Radar SL Order: BUY {quantity} shares at Trigger: ₹{stop_loss:.2f}")
        self.active_trades[symbol] = {
            "entry": price,
            "sl": stop_loss,
            "target": target,
            "qty": quantity,
            "direction": "SELL",
            "status": "SIMULATED",
            "strategy": "RADAR"
        }
    else:
        # Route live order
        self.place_kite_sell_bracket_defense(symbol, quantity, price, stop_loss, target)
        if symbol in self.active_trades:
            self.active_trades[symbol]["strategy"] = "RADAR"


