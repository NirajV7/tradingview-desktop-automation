# Capital Allocation & Risk Management Plan: ₹5,00,000 Account

This is the operational risk and allocation blueprint designed specifically for a **₹5,00,000 (5 Lakh)** active trading capital account. 

---

## 🛡️ Core Risk Parameters (The Circuit Breakers)

| Parameter | Percentage | Value (INR) | Rationale |
| :--- | :---: | :---: | :--- |
| **Total Cash Capital** | 100% | **₹5,00,000** | Your actual account equity. |
| **Max Risk Per Trade** | 0.5% to 1.0% | **₹2,500 to ₹5,000** | Limit loss to ensure 100+ trades survival. |
| **Max Daily Loss Limit** | 2.5% | **₹12,500** | Enforced circuit breaker. Stop trading if hit. |
| **Max Active Trades** | — | **3 Trades** | Limits concentration and correlation risk. |
| **Max Total Exposure Cap**| 3.5x Cash | **₹17,500** per trade / **₹17,50,000** total | Capping total exposure prevents tail-risk blowups. |

---

## 🧮 Live Sizing & Deployment Calculator

For any stock select, determine quantity using this exact flow:

### Sizing Formula:
Quantity = (₹2,500 Conservative Risk or ₹5,000 Max Risk) divided by (Entry Price - Stop Loss Price)

### Examples of Sizing on a ₹5,00,000 Account (using 0.5% Risk = ₹2,500):

| Stock Price (INR) | Stop Loss Width (INR) | Risk Per Share (INR) | **Quantity to Buy/Short** | **Total Exposure (Value)** | **Margin Blocked (5x)** |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **₹200** | ₹4 | ₹4 | **625 shares** | ₹1,25,000 | **₹25,000** |
| **₹500** | ₹10 | ₹10 | **250 shares** | ₹1,25,000 | **₹25,000** |
| **₹1,000** | ₹20 | ₹20 | **125 shares** | ₹1,25,000 | **₹25,000** |
| **₹3,000** | ₹60 | ₹60 | **41 shares** | ₹1,23,000 | **₹24,600** |

---

## ⏱️ Daily Execution Protocol

1. **Trade Sizing Discipline**: Never guess the quantity.
2. **MIS (Intraday) Mode Only**: Ensure all orders are placed as **MIS** (Margin Intraday Square-off) to get the 5x leverage benefits.
3. **The 3-Trade Cap**:
   * If you have 3 trades running, do not enter a 4th, even if a stock from your watchlist is flying.
   * Free up a slot by squaring off an active trade or trailing the stop loss of an active trade to cost/profit before entering a new one.
4. **Leverage Utilization**:
   * Running 3 concurrent trades at ₹25,000 margin each blocks **₹75,000** of your cash.
   * You will see **₹4,25,000 free cash** in your account. **Do not touch it.** That cash is your psychological and draw-down safety buffer.

---

## ⏱️ The 15-Minute Morning Sizing Flow (Instant Calculation)

To prevent panic at 9:30 AM when a stock breaks out/down, utilize this quiet **15-minute preparation window**:

1. **9:15 AM - 9:30 AM (The Watch Phase)**: 
   * Do nothing. Watch the first 15-minute candle form on your watchlist stocks.
2. **9:28 AM (The Calc Phase)**:
   * Select the **1 or 2 stocks** that are trading closest to their 15-minute highs (for longs) or lows (for shorts).
   * Note the exact High and Low prices of their 15-minute candles.
   * **Calculate risk per share**: `High - Low = Risk Per Share`.
   * **Write down the Quantity**: Divide your per-trade risk (e.g., ₹2,500) by the risk per share.
   * *Example*: At 9:29 AM, `TMPV` has a 15m High of `358.5` and a 15m Low of `353.5`. 
     * `Risk per share = ₹5.00`.
     * `Quantity = ₹2,500 / ₹5 = 500 shares`.
   * **Result**: You now have the exact quantity (`500 shares`) written down *before* any trigger happens. If price breaks `358.5` at 9:30 AM, you execute immediately without hesitation.

---

## 🔄 Multi-Trade Sizing Protocol (Entering Trade 2 & 3)

If you are already running Trade 1, and Trade 2 triggers:

### 1. The Core Rule: Sizing is Independent
* **Every trade is treated as an independent probability event.** 
* **Do NOT reduce your risk or quantity** on Trade 2. Size Trade 2 with the exact same risk (e.g., **₹2,500**) based on its own entry and Stop Loss levels.
* Your ₹5,00,000 account is mathematically designed to hold up to **3 concurrent trades**, each carrying ₹2,500 of risk (Total maximum active risk = **₹7,500 or 1.5% of capital**).

### 2. The "Risk-Free" Trailing Lock
To run multiple trades with absolute safety, use this trailing mechanism:
* **The 1:1 Rule**: If Trade 1 moves in your favor and reaches a 1:1 Risk-to-Reward ratio (e.g., you are up ₹2,500 on paper):
  * **Action**: Immediately trail the Stop Loss of Trade 1 to your **entry price (break-even)**.
  * **Result**: Trade 1 now has **zero downside risk**.
  * **Benefit**: Your active risk in the market drops from ₹7,500 back to ₹5,000, freeing up your risk capacity to enter Trade 3 with complete peace of mind.

---

## 📈 ADR-Based Trade Management (Trailing & Scale-Outs)

Average Daily Range (ADR) represents the statistical daily average movement of a stock. Enforcing ADR boundaries keeps your targets realistic and protects your capital from momentum exhaustion.

### The Intraday ADR Exhaustion Trailing Protocol
When your trade moves in your favor, monitor its exhaustion relative to the stock's absolute ADR from the daily open/low:
* **70% ADR Exhaustion Lock**:
  * **Trigger**: If the price achieves greater than or equal to 70% of the absolute ADR expansion from the Daily Open (or Daily Low), **instantly trail your stop loss to break-even (cost)**.
  * **Result**: This locks in a risk-free trade, protecting your position against high-velocity intraday reversals (like today's Trade 1 on CHAMBLFERT).
* **75% ADR Exhaustion Profit Scale-Out (Winner)**:
  * **Trigger**: If the price reaches greater than or equal to 75% of the ADR expansion from Open/Low, **book 50% to 100% of your position**.
  * **Rationale**: At 75% ADR, the stock has completed the vast majority of its typical daily movement. Booking here secures high-probability profits (typically positive 0.7R to positive 1.5R) instead of watching the trade reverse into a scratch.


