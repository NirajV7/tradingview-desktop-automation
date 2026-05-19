import os
from datetime import datetime
import pandas as pd
import config

def audit_active_trades(self):
    """Audits active positions against ADR Trailing Stop and Scale-Out rules."""
    if not self.active_trades:
        return

    try:
        if not os.path.exists(config.FYERS_INDICATORS_5M):
            return
        df = pd.read_csv(config.FYERS_INDICATORS_5M)
    except Exception as e:
        print(f"⚠️ Error reading indicators CSV during active trade audit: {e}")
        return

    active_symbols = list(self.active_trades.keys())

    for symbol in active_symbols:
        trade = self.active_trades[symbol]
        symbol_rows = df[df["symbol"].apply(lambda s: (s.split(":")[1].split("-EQ")[0] if ":" in s else s) == symbol)]
        if symbol_rows.empty:
            continue

        latest = symbol_rows.iloc[-1]
        current_price = float(latest["price"])
        
        try:
            adr_abs = float(latest["adr_abs"])
        except (KeyError, ValueError, TypeError):
            try:
                adr_pct = float(latest["adr"])
                adr_abs = current_price * (adr_pct / 100.0)
            except:
                continue

        daily_open = self.get_daily_open_price(symbol)
        if not daily_open:
            continue

        entry = float(trade["entry"])
        sl = float(trade["sl"])
        qty = int(trade["qty"])
        already_trailed = trade.get("already_trailed", False)

        # Rule 0: EOD Mandatory Square-Off at 3:15 PM (15:15:00)
        now_time = datetime.now().time()
        if now_time >= datetime.strptime("15:15:00", "%H:%M:%S").time():
            print(f"\n🚨 >>> 3:15 PM MANDATORY SQUARE-OFF FOR {symbol} <<< 🚨")
            print(f"💰 Current Time: {now_time.strftime('%H:%M:%S')} >= 15:15:00. Booking position of {qty} shares.")
            
            exit_tx = self.kite.TRANSACTION_TYPE_BUY if direction == "SELL" else self.kite.TRANSACTION_TYPE_SELL
            if self.dry_run:
                print(f"   [Simulation Log] Position squared off at Market Price: ₹{current_price:.2f}")
                self.log_trade_to_journal(symbol, entry, current_price, qty, direction=direction, exit_reason="3:15 PM MANDATORY SQUARE-OFF")
                self.completed_trades_today.add(symbol)
                del self.active_trades[symbol]
            else:
                try:
                    sl_order_id = trade.get("sl_id")
                    if sl_order_id:
                        print(f"🧹 Canceling pending SL order {sl_order_id}...")
                        self.kite.cancel_order(
                            variety=self.kite.VARIETY_REGULAR,
                            order_id=sl_order_id
                        )
                    
                    print(f"🛒 Placing Market Exit Order for 3:15 PM Square-off...")
                    exit_order_id = self.kite.place_order(
                        variety=self.kite.VARIETY_REGULAR,
                        exchange=self.kite.EXCHANGE_NSE,
                        tradingsymbol=symbol,
                        transaction_type=exit_tx,
                        quantity=qty,
                        product=self.kite.PRODUCT_MIS,
                        order_type=self.kite.ORDER_TYPE_MARKET
                    )
                    print(f"✅ Squared Off successfully! Order ID: {exit_order_id}")
                    self.log_trade_to_journal(symbol, entry, current_price, qty, direction=direction, exit_reason="3:15 PM MANDATORY SQUARE-OFF", exit_order_id=exit_order_id)
                    self.completed_trades_today.add(symbol)
                    del self.active_trades[symbol]
                except Exception as e:
                    print(f"❌ Failed to square off trade on Zerodha: {e}")
            continue

        is_radar = (trade.get("strategy") == "RADAR")
        if is_radar:
            target = float(trade.get("target", 0.0))
            if direction == "SELL":
                # Stop Loss Hit (Short SL is above entry)
                if current_price >= sl:
                    print(f"\n💥 >>> RADAR SHORT STOP LOSS HIT FOR {symbol} <<< 💥")
                    print(f"📈 Price: ₹{current_price:.2f} >= Stop Loss: ₹{sl:.2f}")
                    if self.dry_run:
                        self.log_trade_to_journal(symbol, entry, sl, qty, direction="SELL", exit_reason="STOP LOSS HIT (RADAR)")
                        del self.active_trades[symbol]
                    else:
                        self.square_off_radar_position(symbol, qty, "BUY", sl, "STOP LOSS HIT (RADAR)")
                    continue
                # Target Hit (Short Target is below entry)
                if current_price <= target:
                    print(f"\n🎉 >>> RADAR SHORT TARGET ACHIEVED FOR {symbol} <<< 🎉")
                    print(f"💰 Price: ₹{current_price:.2f} <= Target: ₹{target:.2f}")
                    if self.dry_run:
                        self.log_trade_to_journal(symbol, entry, current_price, qty, direction="SELL", exit_reason="TARGET ACHIEVED (RADAR)")
                        del self.active_trades[symbol]
                    else:
                        self.square_off_radar_position(symbol, qty, "BUY", current_price, "TARGET ACHIEVED (RADAR)")
                    continue
            else: # direction == "BUY"
                # Stop Loss Hit (Long SL is below entry)
                if current_price <= sl:
                    print(f"\n💥 >>> RADAR LONG STOP LOSS HIT FOR {symbol} <<< 💥")
                    print(f"📉 Price: ₹{current_price:.2f} <= Stop Loss: ₹{sl:.2f}")
                    if self.dry_run:
                        self.log_trade_to_journal(symbol, entry, sl, qty, direction="BUY", exit_reason="STOP LOSS HIT (RADAR)")
                        del self.active_trades[symbol]
                    else:
                        self.square_off_radar_position(symbol, qty, "SELL", sl, "STOP LOSS HIT (RADAR)")
                    continue
                # Target Hit (Long Target is above entry)
                if current_price >= target:
                    print(f"\n🎉 >>> RADAR LONG TARGET ACHIEVED FOR {symbol} <<< 🎉")
                    print(f"💰 Price: ₹{current_price:.2f} >= Target: ₹{target:.2f}")
                    if self.dry_run:
                        self.log_trade_to_journal(symbol, entry, current_price, qty, direction="BUY", exit_reason="TARGET ACHIEVED (RADAR)")
                        del self.active_trades[symbol]
                    else:
                        self.square_off_radar_position(symbol, qty, "SELL", current_price, "TARGET ACHIEVED (RADAR)")
                    continue
            continue

        if direction == "SELL":
            trigger_70_adr = daily_open - (adr_abs * 0.70)
            trigger_75_adr = daily_open - (adr_abs * 0.75)

            # Rule 1: Stop Loss Hit Guard
            if current_price >= sl:
                print(f"\n💥 >>> STOP LOSS HIT FOR {symbol} <<< 💥")
                print(f"📉 Price: ₹{current_price:.2f} >= Stop Loss: ₹{sl:.2f}")
                loss = (sl - entry) * qty
                print(f"💸 Closed out at Stop Loss. Position Loss: -₹{loss:.2f}")
                self.log_trade_to_journal(symbol, entry, sl, qty, direction="SELL", exit_reason="STOP LOSS HIT")
                self.completed_trades_today.add(symbol)
                del self.active_trades[symbol]
                continue

            # Rule 2: 70% ADR Exhaustion Lock -> Trail Stop Loss to break-even (cost)
            if current_price <= trigger_70_adr and not already_trailed:
                print(f"\n🛡️ >>> 70% ADR EXHAUSTION REACHED FOR {symbol} <<< 🛡️")
                print(f"💰 Price: ₹{current_price:.2f} <= 70% ADR Trigger: ₹{trigger_70_adr:.2f} (Open: ₹{daily_open:.2f} - 70% of ADR: ₹{adr_abs:.2f})")
                
                if self.dry_run:
                    print(f"   [Simulation Log] Trailed Stop Loss to break-even (Entry Cost): ₹{entry:.2f} (Originally: ₹{sl:.2f})")
                    self.active_trades[symbol]["sl"] = entry
                    self.active_trades[symbol]["already_trailed"] = True
                else:
                    sl_order_id = trade.get("sl_id")
                    if sl_order_id:
                        try:
                            print(f"🛠️ Modifying Zerodha Pending SL Order {sl_order_id} to Entry Price: ₹{entry:.2f}...")
                            self.kite.modify_order(
                                variety=self.kite.VARIETY_REGULAR,
                                order_id=sl_order_id,
                                order_type=self.kite.ORDER_TYPE_SL,
                                trigger_price=entry,
                                price=entry  # Limit matches trigger (zero buffer)
                            )
                            print(f"✅ Stop Loss successfully trailed to Break-Even (Entry Cost)!")
                            self.active_trades[symbol]["sl"] = entry
                            self.active_trades[symbol]["already_trailed"] = True
                        except Exception as e:
                            print(f"❌ Failed to trail Stop Loss on Zerodha: {e}")

            # Rule 3: 75% ADR Exhaustion profit Scale-Out -> Exit position completely
            if current_price <= trigger_75_adr:
                print(f"\n🎉 >>> 75% ADR EXHAUSTION WINNER FOR {symbol} <<< 🎉")
                print(f"💰 Price: ₹{current_price:.2f} <= 75% ADR Trigger: ₹{trigger_75_adr:.2f} (Open: ₹{daily_open:.2f} - 75% of ADR: ₹{adr_abs:.2f})")
                print(f"🚀 Booking 100% position profit of {qty} shares!")

                if self.dry_run:
                    print(f"   [Simulation Log] Position squared off at Market Price: ₹{current_price:.2f}")
                    self.log_trade_to_journal(symbol, entry, current_price, qty, direction="SELL", exit_reason="ADR TARGET REACHED")
                    del self.active_trades[symbol]
                else:
                    try:
                        sl_order_id = trade.get("sl_id")
                        if sl_order_id:
                            print(f"🧹 Canceling pending SL order {sl_order_id}...")
                            self.kite.cancel_order(
                                variety=self.kite.VARIETY_REGULAR,
                                order_id=sl_order_id
                            )
                        
                        print(f"🛒 Placing Market Exit Order to Book Profit...")
                        exit_order_id = self.kite.place_order(
                            variety=self.kite.VARIETY_REGULAR,
                            exchange=self.kite.EXCHANGE_NSE,
                            tradingsymbol=symbol,
                            transaction_type=self.kite.TRANSACTION_TYPE_BUY,
                            quantity=qty,
                            product=self.kite.PRODUCT_MIS,
                            order_type=self.kite.ORDER_TYPE_MARKET
                        )
                        print(f"✅ Squared Off successfully! Order ID: {exit_order_id}")
                        self.log_trade_to_journal(symbol, entry, current_price, qty, direction="SELL", exit_reason="ADR TARGET REACHED", exit_order_id=exit_order_id)
                        self.completed_trades_today.add(symbol)
                        del self.active_trades[symbol]
                    except Exception as e:
                        print(f"❌ Failed to square off trade on Zerodha: {e}")

        else:
            # ORIGINAL BUY AUDITING CODE PATH UNTOUCHED
            trigger_70_adr = daily_open + (adr_abs * 0.70)
            trigger_75_adr = daily_open + (adr_abs * 0.75)

            # Rule 1: Stop Loss Hit Guard
            if current_price <= sl:
                print(f"\n💥 >>> STOP LOSS HIT FOR {symbol} <<< 💥")
                print(f"📉 Price: ₹{current_price:.2f} <= Stop Loss: ₹{sl:.2f}")
                loss = (entry - sl) * qty
                print(f"💸 Closed out at Stop Loss. Position Loss: -₹{loss:.2f}")
                self.log_trade_to_journal(symbol, entry, sl, qty, direction="BUY", exit_reason="STOP LOSS HIT")
                self.completed_trades_today.add(symbol)
                del self.active_trades[symbol]
                continue

            # Rule 2: 70% ADR Exhaustion Lock -> Trail Stop Loss to break-even (cost)
            if current_price >= trigger_70_adr and not already_trailed:
                print(f"\n🛡️ >>> 70% ADR EXHAUSTION REACHED FOR {symbol} <<< 🛡️")
                print(f"💰 Price: ₹{current_price:.2f} >= 70% ADR Trigger: ₹{trigger_70_adr:.2f} (Open: ₹{daily_open:.2f} + 70% of ADR: ₹{adr_abs:.2f})")
                
                if self.dry_run:
                    print(f"   [Simulation Log] Trailed Stop Loss to break-even (Entry Cost): ₹{entry:.2f} (Originally: ₹{sl:.2f})")
                    self.active_trades[symbol]["sl"] = entry
                    self.active_trades[symbol]["already_trailed"] = True
                else:
                    sl_order_id = trade.get("sl_id")
                    if sl_order_id:
                        try:
                            print(f"🛠️ Modifying Zerodha Pending SL Order {sl_order_id} to Entry Price: ₹{entry:.2f}...")
                            self.kite.modify_order(
                                variety=self.kite.VARIETY_REGULAR,
                                order_id=sl_order_id,
                                order_type=self.kite.ORDER_TYPE_SL,
                                trigger_price=entry,
                                price=entry  # Limit matches trigger (zero buffer)
                            )
                            print(f"✅ Stop Loss successfully trailed to Break-Even (Entry Cost)!")
                            self.active_trades[symbol]["sl"] = entry
                            self.active_trades[symbol]["already_trailed"] = True
                        except Exception as e:
                            print(f"❌ Failed to trail Stop Loss on Zerodha: {e}")

            # Rule 3: 75% ADR Exhaustion profit Scale-Out -> Exit position completely
            if current_price >= trigger_75_adr:
                print(f"\n🎉 >>> 75% ADR EXHAUSTION WINNER FOR {symbol} <<< 🎉")
                print(f"💰 Price: ₹{current_price:.2f} >= 75% ADR Trigger: ₹{trigger_75_adr:.2f} (Open: ₹{daily_open:.2f} + 75% of ADR: ₹{adr_abs:.2f})")
                print(f"🚀 Booking 100% position profit of {qty} shares!")

                if self.dry_run:
                    print(f"   [Simulation Log] Position squared off at Market Price: ₹{current_price:.2f}")
                    self.log_trade_to_journal(symbol, entry, current_price, qty, direction="BUY", exit_reason="ADR TARGET REACHED")
                    del self.active_trades[symbol]
                else:
                    try:
                        sl_order_id = trade.get("sl_id")
                        if sl_order_id:
                            print(f"🧹 Canceling pending SL order {sl_order_id}...")
                            self.kite.cancel_order(
                                variety=self.kite.VARIETY_REGULAR,
                                order_id=sl_order_id
                            )
                        
                        print(f"🛒 Placing Market Exit Order to Book Profit...")
                        exit_order_id = self.kite.place_order(
                            variety=self.kite.VARIETY_REGULAR,
                            exchange=self.kite.EXCHANGE_NSE,
                            tradingsymbol=symbol,
                            transaction_type=self.kite.TRANSACTION_TYPE_SELL,
                            quantity=qty,
                            product=self.kite.PRODUCT_MIS,
                            order_type=self.kite.ORDER_TYPE_MARKET
                        )
                        print(f"✅ Squared Off successfully! Order ID: {exit_order_id}")
                        self.log_trade_to_journal(symbol, entry, current_price, qty, direction="BUY", exit_reason="ADR TARGET REACHED", exit_order_id=exit_order_id)
                        self.completed_trades_today.add(symbol)
                        del self.active_trades[symbol]
                    except Exception as e:
                        print(f"❌ Failed to square off trade on Zerodha: {e}")

def square_off_radar_position(self, symbol, qty, exit_direction, exit_price, reason):
    try:
        trade = self.active_trades.get(symbol)
        if not trade:
            return
        sl_order_id = trade.get("sl_id")
        if sl_order_id:
            print(f"🧹 Canceling pending SL order {sl_order_id}...")
            try:
                self.kite.cancel_order(
                    variety=self.kite.VARIETY_REGULAR,
                    order_id=sl_order_id
                )
            except Exception as ex:
                print(f"⚠️ Failed to cancel pending SL: {ex}")
        
        target_order_id = trade.get("target_id")
        if target_order_id:
            print(f"🧹 Canceling pending target order {target_order_id}...")
            try:
                self.kite.cancel_order(
                    variety=self.kite.VARIETY_REGULAR,
                    order_id=target_order_id
                )
            except Exception as ex:
                print(f"⚠️ Failed to cancel target: {ex}")

        print(f"🛒 Placing Market Exit Order ({exit_direction}) to Square off Radar trade...")
        exit_order_id = self.kite.place_order(
            variety=self.kite.VARIETY_REGULAR,
            exchange=self.kite.EXCHANGE_NSE,
            tradingsymbol=symbol,
            transaction_type=exit_direction,
            quantity=qty,
            product=self.kite.PRODUCT_MIS,
            order_type=self.kite.ORDER_TYPE_MARKET
        )
        print(f"✅ Squared Off successfully! Order ID: {exit_order_id}")
        self.log_trade_to_journal(symbol, trade["entry"], exit_price, qty, direction=trade["direction"], exit_reason=reason, exit_order_id=exit_order_id)
        self.completed_trades_today.add(symbol)
        del self.active_trades[symbol]
    except Exception as e:
        print(f"❌ Failed to square off Radar trade: {e}")

