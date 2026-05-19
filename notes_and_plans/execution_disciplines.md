# The Hidden Edges: Execution Disciplines & Costs

These are the core operational edges that separate professional quantitative desks from retail traders. Enforcing these rules protects your **₹5,00,000 capital** from invisible leaks.

---

### 1. The Transaction Cost Drag (Why Stock Price Matters)

Intraday trading incurs friction costs: Brokerage, STT (Securities Transaction Tax), GST, Exchange Transaction Charges, and Stamp Duty.

* **The Leak**: For stocks priced under **₹150** (e.g., `CANBK`, `MOTHERSON`), you must trade a very large quantity of shares to deploy your capital. This high quantity creates huge absolute volume turnover, which dramatically increases your STT and exchange charges. Government taxes can eat up to **10% to 15% of your gross profits** on low-priced stocks.
* **The Quant Edge**: **Prioritize stocks priced above ₹300.** 
  * Trading `MUTHOOTFIN` (₹3,311) or `UNITDSPR` (₹1,320) reduces your absolute share volume, lowering your transaction cost drag to less than **2% to 3% of your gross profits**. This is a massive structural advantage over time.

---

### 2. The Feedback Loop: Daily Trade Journal Template

You cannot optimize what you do not measure. You must track your statistics to verify your edge.

Create a daily markdown file in `selected_stocks/` using this exact log format:

| Date | Stock | Type (MIS) | Direction | Entry | SL | Target (1:2) | Exit Price | P&L (INR) | Notes/Emotions |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 18-May | `TMPV` | MIS | LONG | 358.5 | 353.5 | 368.5 | 368.5 | +₹5,000 | Clean ORB breakout, hit target. |
| 18-May | `EPL` | MIS | SHORT | 214.0 | 217.0 | 208.0 | 217.0 | -₹2,500 | Hit SL. Retested VWAP and surged. |

* **Monthly Metrics to Watch**:
  * **Win Rate**: Aim for greater than or equal to 45%.
  * **Average Winner vs. Average Loser**: Must be greater than or equal to 1.5 times.

---

### 3. Execution Psychology: "Set-and-Forget" on Zerodha Kite

The human brain is structurally wired to destroy trading edges:
* **The Trap**: Traders get scared and cut winners early to lock in green, but hold onto losers past their Stop Loss hoping they will bounce. This flips the math against you.
* **The Zerodha Kite Setup**:
  1. **MIS Entry**: Execute your entry using a standard **MIS** (Margin Intraday Square-off) Limit or Market order.
  2. **Double Defense**: Once entered, immediately place two orders in the pending book:
     * A **Stop Loss order (SL or SL-M)** at your risk level.
     * A **Limit target order (LMT)** at your profit target (minimum 1:2 R:R).
  3. **The Pending Book Rule**: Because these are two separate pending orders, **once one is hit (either Target or SL), you must immediately cancel the other order manually.** Failure to do so exposes you to a reverse execution if the price swings back.
  4. **Hands Off (Or ADR Trail)**: Do not modify the levels during the trade *unless* the **ADR Exhaustion Overlay** is triggered. If the price achieves greater than or equal to 70% of the stock's absolute ADR expansion from Open/Low, immediately trail your pending Stop Loss order to **Cost (Break-Even)** to eliminate all downside risk. Removing manual/emotional intervention (outside of statistical ADR rules) stabilizes your win rate.

---

### 4. Macro Alignment (The Nifty Index Tide)

* **The Rule**: "A rising tide lifts all boats; a falling tide sinks them."
* **Intraday Index Gate**:
  * If Nifty is trading **above its intraday VWAP** -> Only trade **LONG** setups from your list. Defer shorts.
  * If Nifty is trading **below its intraday VWAP** -> Only trade **SHORT** setups from your list. Defer longs.
  * If Nifty is flat and chopping within its opening range -> Reduce position sizes by 50%.
