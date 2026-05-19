import os
from datetime import datetime
import config

def log_trade_to_journal(self, symbol, entry_price, exit_price, quantity, direction="BUY", exit_reason="STOP LOSS HIT", entry_order_id=None, exit_order_id=None):
    """
    Logs a completed trade with precise regulatory charges and net PnL down to the paisa inside trade_journal.md.
    Automatically updates total summary statistics at the top of the file.
    """
    # 1. Fetch exact entry & exit charges
    entry_charges = self.fetch_transaction_costs(symbol, quantity, entry_price, "BUY" if direction == "BUY" else "SELL")
    exit_charges = self.fetch_transaction_costs(symbol, quantity, exit_price, "SELL" if direction == "BUY" else "BUY")
    
    total_charges = entry_charges["total"] + exit_charges["total"]
    
    # 2. Calculate Gross and Net PnL
    multiplier = 1 if direction == "BUY" else -1
    gross_pnl = (exit_price - entry_price) * quantity * multiplier
    net_pnl = gross_pnl - total_charges
    
    # Format values
    gross_pnl_str = f"₹{gross_pnl:.2f}" if gross_pnl >= 0 else f"-₹{abs(gross_pnl):.2f}"
    net_pnl_str = f"₹{net_pnl:.2f}" if net_pnl >= 0 else f"-₹{abs(net_pnl):.2f}"
    total_charges_str = f"₹{total_charges:.2f}"
    
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status_str = "🟢 WIN" if net_pnl > 0 else "🔴 LOSS"
    if abs(net_pnl) < 1.0:
        status_str = "⚪ FLAT"
        
    details_cell = (
        f"<details><summary>Charges Breakdown</summary><ul>"
        f"<li>Brokerage: ₹{entry_charges['brokerage'] + exit_charges['brokerage']:.2f}</li>"
        f"<li>STT/CTT: ₹{entry_charges['stt'] + exit_charges['stt']:.2f}</li>"
        f"<li>GST: ₹{entry_charges['gst'] + exit_charges['gst']:.2f}</li>"
        f"<li>Stamp Duty: ₹{entry_charges['stamp_duty'] + exit_charges['stamp_duty']:.2f}</li>"
        f"<li>Exchange Transaction: ₹{entry_charges['exchange_charge'] + exit_charges['exchange_charge']:.2f}</li>"
        f"<li>SEBI Fee: ₹{entry_charges['sebi_fee'] + exit_charges['sebi_fee']:.2f}</li>"
        f"</ul></details>"
    )
    
    # New Row data
    new_row_cols = [
        date_str,
        symbol,
        direction,
        str(quantity),
        f"₹{entry_price:.2f}",
        f"₹{exit_price:.2f}",
        gross_pnl_str,
        total_charges_str,
        net_pnl_str,
        f"{status_str} ({exit_reason})",
        details_cell
    ]
    new_row_line = "| " + " | ".join(new_row_cols) + " |"
    
    # 3. Read existing trade_journal.md or initialize if missing
    journal_path = os.path.join(config.CWD, "trade_journal.md")
    existing_rows = []
    
    if os.path.exists(journal_path):
        try:
            with open(journal_path, "r") as f:
                lines = f.readlines()
            
            # Extract existing rows from the table
            in_table = False
            for line in lines:
                line_stripped = line.strip()
                if line_stripped.startswith("|") and "Symbol" not in line_stripped and "---" not in line_stripped and "Metric" not in line_stripped and "Value" not in line_stripped:
                    # Ensure this is a data row, not headers
                    cols = [c.strip() for c in line_stripped.split("|")[1:-1]]
                    if len(cols) >= 9 and cols[0] != "":
                        existing_rows.append(line_stripped)
        except Exception as e:
            print(f"⚠️ Error reading existing trade journal: {e}")
            
    # Append the new row to existing rows
    existing_rows.append(new_row_line)
    
    # 4. Re-calculate total stats across all history!
    total_trades = len(existing_rows)
    total_gross_pnl = 0.0
    total_charges_acc = 0.0
    total_net_pnl = 0.0
    wins = 0
    total_win_amount = 0.0
    total_loss_amount = 0.0
    
    for row in existing_rows:
        try:
            cols = [c.strip() for c in row.split("|")[1:-1]]
            gross_val = float(cols[6].replace("₹", "").replace(",", "").replace(" ", ""))
            charges_val = float(cols[7].replace("₹", "").replace(",", "").replace(" ", ""))
            net_val = float(cols[8].replace("₹", "").replace(",", "").replace(" ", ""))
            
            total_gross_pnl += gross_val
            total_charges_acc += charges_val
            total_net_pnl += net_val
            
            if net_val > 0:
                wins += 1
                total_win_amount += net_val
            elif net_val < 0:
                total_loss_amount += abs(net_val)
        except Exception as parse_ex:
            print(f"⚠️ Failed to parse row for stats: {row} ({parse_ex})")
            
    win_rate = (wins / total_trades) * 100.0 if total_trades > 0 else 0.0
    profit_factor = (total_win_amount / total_loss_amount) if total_loss_amount > 0 else (total_win_amount if total_win_amount > 0 else 1.0)
    
    # Format overview variables
    tot_gross_pnl_str = f"₹{total_gross_pnl:.2f}" if total_gross_pnl >= 0 else f"-₹{abs(total_gross_pnl):.2f}"
    tot_charges_str = f"₹{total_charges_acc:.2f}"
    tot_net_pnl_str = f"₹{total_net_pnl:.2f}" if total_net_pnl >= 0 else f"-₹{abs(total_net_pnl):.2f}"
    
    # 5. Write the beautiful updated markdown file
    try:
        with open(journal_path, "w") as f:
            f.write(f"# 📊 Institutional Trade Journal & Ledger\n\n")
            f.write(f"This ledger dynamically parses your completed Zerodha trades and logs absolute profit, loss, and transaction costs down to the paisa.\n\n")
            f.write(f"## 📈 System Ledger Overview\n\n")
            f.write(f"| Metric | Value |\n")
            f.write(f"| :--- | :--- |\n")
            f.write(f"| **Total Closed Trades** | {total_trades} |\n")
            f.write(f"| **Net Profit / Loss (PnL)** | **{tot_net_pnl_str}** |\n")
            f.write(f"| **Gross Profit / Loss** | {tot_gross_pnl_str} |\n")
            f.write(f"| **Total Transaction Charges** | {tot_charges_str} |\n")
            f.write(f"| **Win Rate** | {win_rate:.2f}% |\n")
            f.write(f"| **Profit Factor** | {profit_factor:.2f} |\n\n")
            f.write(f"---\n\n")
            f.write(f"## 📜 Historical Logs\n\n")
            f.write(f"| Date/Time | Symbol | Type | Qty | Entry Price | Exit Price | Gross PnL | Charges | Net PnL | Status | Details |\n")
            f.write(f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
            for r in reversed(existing_rows):  # Show latest trade at the top!
                f.write(r + "\n")
        print(f"📊 [JOURNAL] Successfully logged trade for {symbol} to trade_journal.md | Net PnL: {net_pnl_str}")
    except Exception as write_ex:
        print(f"❌ Failed to write trade journal: {write_ex}")
