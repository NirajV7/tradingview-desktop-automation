import time

def place_kite_bracket_defense(self, symbol, quantity, entry_price, stop_loss, target):
    """Places primary MIS entry and pending SL stop-loss order in Zerodha Kite."""
    try:
        # 1. Primary Entry Order (Using Marketable LIMIT order to comply with Zerodha API protection)
        print(f"🛒 Placing Primary MIS Entry Order for {symbol}...")
        limit_price = round(round((entry_price * 1.005) / 0.05) * 0.05, 2)
        entry_order_id = self.kite.place_order(
            variety=self.kite.VARIETY_REGULAR,
            exchange=self.kite.EXCHANGE_NSE,
            tradingsymbol=symbol,
            transaction_type=self.kite.TRANSACTION_TYPE_BUY,
            quantity=quantity,
            product=self.kite.PRODUCT_MIS,
            order_type=self.kite.ORDER_TYPE_LIMIT,
            price=limit_price
        )
        print(f"✅ Entry Order placed successfully. Order ID: {entry_order_id}")

        # 2. Wait and check if BUY order is fully filled/COMPLETE
        filled = False
        for attempt in range(20):  # Wait up to 10 seconds (20 * 0.5s)
            time.sleep(0.5)
            try:
                history = self.kite.order_history(entry_order_id)
                if history:
                    status = history[-1].get("status")
                    print(f"   [Order Check] BUY Order {entry_order_id} status: {status}")
                    if status == "COMPLETE":
                        filled = True
                        break
                    elif status in ["REJECTED", "CANCELLED"]:
                        print(f"❌ Primary Entry Order was {status}. Aborting SL placement.")
                        return
            except Exception as ex:
                print(f"⚠️ Error checking order history: {ex}")
        
        # If still not marked COMPLETE, double check live positions book
        if not filled:
            print(f"⚠️ Order status not COMPLETE in history. Double-checking active positions book...")
            try:
                positions = self.kite.positions()
                net_positions = positions.get("net", [])
                for pos in net_positions:
                    if pos.get("tradingsymbol") == symbol and abs(int(pos.get("quantity", 0))) >= quantity:
                        print(f"✅ Found filled position for {symbol} in positions book! Quantity: {pos.get('quantity')}")
                        filled = True
                        break
            except Exception as pos_ex:
                print(f"⚠️ Error checking live positions book: {pos_ex}")

        if not filled:
            print(f"❌ Primary Entry Order {entry_order_id} not filled in history or positions book within 10 seconds.")
            print(f"🧹 Canceling pending entry order {entry_order_id} to prevent delayed execution...")
            try:
                self.kite.cancel_order(
                    variety=self.kite.VARIETY_REGULAR,
                    order_id=entry_order_id
                )
                print("✅ Pending Entry Order canceled successfully. Aborting SL placement.")
            except Exception as cancel_ex:
                print(f"⚠️ Failed to cancel pending entry order: {cancel_ex}")
                # If cancel failed, it might have filled at the very last second. Check positions one last time.
                try:
                    time.sleep(1.0)  # Short grace period
                    positions = self.kite.positions()
                    net_positions = positions.get("net", [])
                    for pos in net_positions:
                        if pos.get("tradingsymbol") == symbol and abs(int(pos.get("quantity", 0))) >= quantity:
                            print(f"✅ Post-cancel check: Found filled position for {symbol}! Proceeding to SL placement.")
                            filled = True
                            break
                except Exception as pos_ex2:
                    print(f"⚠️ Error checking positions during post-cancel fallback: {pos_ex2}")
            
            if not filled:
                return

        # 3. Place Stop Loss Pending Order (Standard SL Limit) with 3 retries
        print(f"🛡️ Placing Pending SL Stop Loss Order at Trigger: ₹{stop_loss:.2f}...")
        sl_order_id = None
        for sl_attempt in range(3):
            try:
                sl_order_id = self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange=self.kite.EXCHANGE_NSE,
                    tradingsymbol=symbol,
                    transaction_type=self.kite.TRANSACTION_TYPE_SELL,
                    quantity=quantity,
                    product=self.kite.PRODUCT_MIS,
                    order_type=self.kite.ORDER_TYPE_SL,
                    trigger_price=stop_loss,
                    price=stop_loss  # Limit price matches trigger (zero buffer)
                )
                print(f"🚀 SL Stop Loss Order active in Zerodha Pending Book! Order ID: {sl_order_id}")
                break
            except Exception as sl_err:
                print(f"⚠️ Attempt {sl_attempt + 1}/3 to place Stop Loss failed: {sl_err}")
                if sl_attempt < 2:
                    time.sleep(1.0)
                else:
                    # 3 retries exhausted -> Emergency Square-Off
                    print(f"🚨 CRITICAL: Failed to place Stop Loss order after 3 retries!")
                    print(f"🛒 Initiating EMERGENCY MARKET SQUARE-OFF to protect capital...")
                    try:
                        exit_order_id = self.kite.place_order(
                            variety=self.kite.VARIETY_REGULAR,
                            exchange=self.kite.EXCHANGE_NSE,
                            tradingsymbol=symbol,
                            transaction_type=self.kite.TRANSACTION_TYPE_SELL,
                            quantity=quantity,
                            product=self.kite.PRODUCT_MIS,
                            order_type=self.kite.ORDER_TYPE_MARKET
                        )
                        print(f"🚨 EMERGENCY: Position squared off successfully! Emergency Order ID: {exit_order_id}")
                    except Exception as emergency_error:
                        print(f"🚨 DANGER: EMERGENCY SQUARE-OFF FAILED! {emergency_error}")
                        print(f"🚨 Niraj, check your Zerodha app immediately for open NSE:{symbol}-EQ position!")
                    raise sl_err
        
        # Record active trade state only if we successfully placed the SL
        if sl_order_id:
            self.active_trades[symbol] = {
                "entry": entry_price,
                "sl": stop_loss,
                "target": target,
                "qty": quantity,
                "entry_id": entry_order_id,
                "sl_id": sl_order_id,
                "status": "LIVE"
            }
    except Exception as e:
        print(f"❌ Failed to place orders on Zerodha: {e}")
