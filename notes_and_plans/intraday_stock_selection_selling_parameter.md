# Intraday Stock Selection: Selling (Short) Parameter Setup

This setup is designed to identify structurally weak, high-volume distribution candidates on the daily timeframe the night before, for short-selling execution the next trading day.

---

## 🛠️ Chartink Screener Conditions

Input these exact filters into Chartink in the Cash segment:

```text
Stock passes all of the below filters in cash segment:

1. [ ] Market Cap Greater than Number 5000
2. [ ] Daily Close Greater than Number 100
3. [ ] Daily Close Less than equal to Daily Ema( Daily Close, 20 )
4. [ ] Daily Close Less than equal to Daily Ema( Daily Close, 50 )
5. [ ] Daily Rsi( 14 ) Less than equal to Number 45
6. [ ] Daily Rsi( 14 ) Greater than equal to Number 35
7. [ ] Daily Close Less than Daily Open
8. [ ] Daily Volume Greater than Daily Sma( Daily Volume, 20 )
9. [ ] Daily Volume Greater than 1 day ago Volume
```

### ⚡ Optional Filter: Relative Weakness (vs Nifty 50)
Add this filter if you want to restrict the list strictly to the weakest stocks underperforming the broad index:
```text
Latest ( Close / Nifty 50 Close ) Less than Latest Ema( ( Close / Nifty 50 Close ) , 20 )
```

---

## 📉 Quantitative Rationale

* **RSI Distribution Slipstream (35 to 45)**: Captures the acceleration phase of a daily downtrend *before* it reaches the extreme oversold zone (less than or equal to 30), which is prone to sudden short-covering bounces.
* **EMA 20 & 50 Resistance Confluence**: Ensures alignment with the primary medium-term structural downtrend (price is below major averages).
* **Double Volume Surge**: Accelerating volume on a red daily candle confirms **institutional distribution** (heavy block selling).
* **Liquidity Filter**: Retaining greater than or equal to ₹5,000 Crore Mcap is critical for short-selling to ensure high intraday liquidity, tight bid-ask spreads, and zero issues with stock lending/short margin availability.

---

## ⏱️ Execution Guide (Intraday Shorting Rules)

### 1. Opening Gate (Avoid Morning Short Squeezes)
* **Rule**: **Do NOT short-sell the open.** Weak stocks sometimes open with a gap-down, followed by an immediate relief rally/short squeeze as overnight shorts book profits.
* **Wait**: Let the market print its first **15-minute candle** (9:15 AM - 9:30 AM).

### 2. The Entry Gate (Opening Range Breakout - Bearish ORB)
* Once the 15-minute range is established:
  * **Trigger**: Short sell when the price breaks below the low of the first 15-minute candle.
  * **Volume Confirmation**: The breakdown candle must show expanding volume compared to average 1-minute volumes.
  * **VWAP Rule**: Ensure the stock is trading strictly **below its intraday VWAP**.

### 3. Risk Management & Stop Loss
* **Stop Loss (SL)**: Place the SL at the **high of the 15-minute opening candle**, or at the intraday high if the stock pulled back to VWAP and got rejected.
* **Target**: Target a minimum of **1:1.5 or 1:2 Risk-to-Reward (R:R)**.
* **Time Exit**: Always **square off all short positions automatically by 3:15 PM**; holding intraday shorts overnight in the Indian cash segment is not allowed (will trigger auction penalties).
