import os
import csv
from datetime import datetime
import config

def migrate_md_to_csv_if_needed():
    """Migrates any existing markdown records in trade_journal.md to trade_journal.csv once."""
    csv_path = config.TRADE_JOURNAL_CSV
    journal_path = os.path.join(config.CWD, "trade_journal.md")
    
    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
        return
        
    if not os.path.exists(journal_path):
        return
        
    print("⏳ [JOURNAL] Migrating legacy trade_journal.md to trade_journal.csv...")
    try:
        with open(journal_path, "r") as f:
            lines = f.readlines()
            
        staged_rows = []
        for line in lines:
            line_stripped = line.strip()
            if line_stripped.startswith("|") and "Symbol" not in line_stripped and "---" not in line_stripped and "Metric" not in line_stripped and "Value" not in line_stripped:
                cols = [c.strip() for c in line_stripped.split("|")[1:-1]]
                if len(cols) >= 10 and cols[0] != "":
                    timestamp = cols[0]
                    symbol = cols[1]
                    direction = cols[2]
                    quantity = int(cols[3])
                    entry_price = float(cols[4].replace("₹", "").replace(",", ""))
                    exit_price = float(cols[5].replace("₹", "").replace(",", ""))
                    gross_pnl = float(cols[6].replace("₹", "").replace(",", ""))
                    total_charges = float(cols[7].replace("₹", "").replace(",", ""))
                    net_pnl = float(cols[8].replace("₹", "").replace(",", ""))
                    
                    status_part = cols[9]
                    exit_reason = "STOP LOSS HIT"
                    if "(" in status_part:
                        exit_reason = status_part.split("(")[-1].replace(")", "").strip()
                    elif "WIN" in status_part:
                        exit_reason = "TARGET HIT"
                        
                    details = cols[10]
                    
                    def extract_fee(label, text):
                        try:
                            if label in text:
                                return float(text.split(label)[1].split("</li>")[0].replace("₹", "").replace(" ", ""))
                            return 0.0
                        except:
                            return 0.0
                            
                    brokerage = extract_fee("Brokerage: ₹", details)
                    stt = extract_fee("STT/CTT: ₹", details)
                    gst = extract_fee("GST: ₹", details)
                    stamp_duty = extract_fee("Stamp Duty: ₹", details)
                    exchange_charge = extract_fee("Exchange Transaction: ₹", details)
                    sebi_fee = extract_fee("SEBI Fee: ₹", details)
                    
                    staged_rows.append({
                        "timestamp": timestamp,
                        "symbol": symbol,
                        "direction": direction,
                        "quantity": quantity,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "gross_pnl": gross_pnl,
                        "brokerage": brokerage,
                        "stt": stt,
                        "gst": gst,
                        "stamp_duty": stamp_duty,
                        "exchange_charge": exchange_charge,
                        "sebi_fee": sebi_fee,
                        "total_charges": total_charges,
                        "net_pnl": net_pnl,
                        "exit_reason": exit_reason,
                        "entry_order_id": "",
                        "exit_order_id": ""
                    })
        
        if staged_rows:
            staged_rows.reverse()
            os.makedirs(os.path.dirname(csv_path), exist_ok=True)
            fieldnames = [
                "timestamp", "symbol", "direction", "quantity", "entry_price", "exit_price",
                "gross_pnl", "brokerage", "stt", "gst", "stamp_duty", "exchange_charge",
                "sebi_fee", "total_charges", "net_pnl", "exit_reason", "entry_order_id", "exit_order_id"
            ]
            with open(csv_path, "w", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for r in staged_rows:
                    writer.writerow(r)
            print(f"✅ [JOURNAL] Migrated {len(staged_rows)} trades to {csv_path}")
    except Exception as e:
        print(f"⚠️ Failed to migrate legacy journal to CSV: {e}")

def log_trade_to_journal(self, symbol, entry_price, exit_price, quantity, direction="BUY", exit_reason="STOP LOSS HIT", entry_order_id=None, exit_order_id=None):
    """
    Logs a completed trade with precise regulatory charges and net PnL down to the paisa inside trade_journal.csv.
    Regenerates trade_journal.md with updated stats and interactive breakdowns.
    """
    # 1. Migrate legacy markdown history first if CSV doesn't exist
    migrate_md_to_csv_if_needed()
    
    # 2. Fetch entry & exit charges
    entry_charges = self.fetch_transaction_costs(symbol, quantity, entry_price, "BUY" if direction == "BUY" else "SELL")
    exit_charges = self.fetch_transaction_costs(symbol, quantity, exit_price, "SELL" if direction == "BUY" else "BUY")
    total_charges = entry_charges["total"] + exit_charges["total"]
    
    # 3. Calculate Gross and Net PnL
    multiplier = 1 if direction == "BUY" else -1
    gross_pnl = (exit_price - entry_price) * quantity * multiplier
    net_pnl = gross_pnl - total_charges
    
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    csv_path = config.TRADE_JOURNAL_CSV
    
    # 4. Write new row to CSV
    row_dict = {
        "timestamp": date_str,
        "symbol": symbol,
        "direction": direction,
        "quantity": quantity,
        "entry_price": round(entry_price, 2),
        "exit_price": round(exit_price, 2),
        "gross_pnl": round(gross_pnl, 2),
        "brokerage": round(entry_charges["brokerage"] + exit_charges["brokerage"], 2),
        "stt": round(entry_charges["stt"] + exit_charges["stt"], 2),
        "gst": round(entry_charges["gst"] + exit_charges["gst"], 2),
        "stamp_duty": round(entry_charges["stamp_duty"] + exit_charges["stamp_duty"], 2),
        "exchange_charge": round(entry_charges["exchange_charge"] + exit_charges["exchange_charge"], 2),
        "sebi_fee": round(entry_charges["sebi_fee"] + exit_charges["sebi_fee"], 2),
        "total_charges": round(total_charges, 2),
        "net_pnl": round(net_pnl, 2),
        "exit_reason": exit_reason,
        "entry_order_id": entry_order_id or "",
        "exit_order_id": exit_order_id or ""
    }
    
    fieldnames = [
        "timestamp", "symbol", "direction", "quantity", "entry_price", "exit_price",
        "gross_pnl", "brokerage", "stt", "gst", "stamp_duty", "exchange_charge",
        "sebi_fee", "total_charges", "net_pnl", "exit_reason", "entry_order_id", "exit_order_id"
    ]
    
    file_exists = os.path.exists(csv_path)
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    
    try:
        with open(csv_path, "a", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row_dict)
    except Exception as e:
        print(f"❌ Failed to write trade to CSV: {e}")
        return
        
    # 5. Read all CSV entries to calculate summary metrics
    csv_rows = []
    try:
        with open(csv_path, "r") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                csv_rows.append({
                    "timestamp": row["timestamp"],
                    "symbol": row["symbol"],
                    "direction": row["direction"],
                    "quantity": int(row["quantity"]),
                    "entry_price": float(row["entry_price"]),
                    "exit_price": float(row["exit_price"]),
                    "gross_pnl": float(row["gross_pnl"]),
                    "brokerage": float(row["brokerage"]),
                    "stt": float(row["stt"]),
                    "gst": float(row["gst"]),
                    "stamp_duty": float(row["stamp_duty"]),
                    "exchange_charge": float(row["exchange_charge"]),
                    "sebi_fee": float(row["sebi_fee"]),
                    "total_charges": float(row["total_charges"]),
                    "net_pnl": float(row["net_pnl"]),
                    "exit_reason": row["exit_reason"],
                    "entry_order_id": row.get("entry_order_id", ""),
                    "exit_order_id": row.get("exit_order_id", "")
                })
    except Exception as e:
        print(f"❌ Failed to read CSV for stats generation: {e}")
        return
        
    total_trades = len(csv_rows)
    total_gross_pnl = sum(r["gross_pnl"] for r in csv_rows)
    total_charges_acc = sum(r["total_charges"] for r in csv_rows)
    total_net_pnl = sum(r["net_pnl"] for r in csv_rows)
    
    wins = len([r for r in csv_rows if r["net_pnl"] > 0])
    total_win_amount = sum(r["net_pnl"] for r in csv_rows if r["net_pnl"] > 0)
    total_loss_amount = sum(abs(r["net_pnl"]) for r in csv_rows if r["net_pnl"] < 0)
    
    win_rate = (wins / total_trades) * 100.0 if total_trades > 0 else 0.0
    profit_factor = (total_win_amount / total_loss_amount) if total_loss_amount > 0 else (total_win_amount if total_win_amount > 0 else 1.0)
    
    tot_gross_pnl_str = f"₹{total_gross_pnl:.2f}" if total_gross_pnl >= 0 else f"-₹{abs(total_gross_pnl):.2f}"
    tot_charges_str = f"₹{total_charges_acc:.2f}"
    tot_net_pnl_str = f"₹{total_net_pnl:.2f}" if total_net_pnl >= 0 else f"-₹{abs(total_net_pnl):.2f}"
    
    # 6. Generate the Markdown table lines
    md_lines = []
    for r in reversed(csv_rows):
        status_str = "🟢 WIN" if r["net_pnl"] > 0 else "🔴 LOSS"
        if abs(r["net_pnl"]) < 1.0:
            status_str = "⚪ FLAT"
            
        details_cell = (
            f"<details><summary>Charges Breakdown</summary><ul>"
            f"<li>Brokerage: ₹{r['brokerage']:.2f}</li>"
            f"<li>STT/CTT: ₹{r['stt']:.2f}</li>"
            f"<li>GST: ₹{r['gst']:.2f}</li>"
            f"<li>Stamp Duty: ₹{r['stamp_duty']:.2f}</li>"
            f"<li>Exchange Transaction: ₹{r['exchange_charge']:.2f}</li>"
            f"<li>SEBI Fee: ₹{r['sebi_fee']:.2f}</li>"
            f"</ul></details>"
        )
        
        gross_str = f"₹{r['gross_pnl']:.2f}" if r['gross_pnl'] >= 0 else f"-₹{abs(r['gross_pnl']):.2f}"
        net_str = f"₹{r['net_pnl']:.2f}" if r['net_pnl'] >= 0 else f"-₹{abs(r['net_pnl']):.2f}"
        
        row_cols = [
            r["timestamp"],
            r["symbol"],
            r["direction"],
            str(r["quantity"]),
            f"₹{r['entry_price']:.2f}",
            f"₹{r['exit_price']:.2f}",
            gross_str,
            f"₹{r['total_charges']:.2f}",
            net_str,
            f"{status_str} ({r['exit_reason']})",
            details_cell
        ]
        md_lines.append("| " + " | ".join(row_cols) + " |")
        
    # 7. Write the dynamic Markdown file
    journal_path = os.path.join(config.CWD, "trade_journal.md")
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
            for line in md_lines:
                f.write(line + "\n")
        print(f"📊 [JOURNAL] Successfully logged trade for {symbol} to CSV and regenerated trade_journal.md")
    except Exception as write_ex:
        print(f"❌ Failed to write trade journal markdown: {write_ex}")

