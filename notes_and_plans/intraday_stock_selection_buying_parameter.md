# Intraday Stock Selection: Buying Parameter Setup

This setup is designed to identify high-probability momentum-expansion candidates on the daily timeframe the night before, for long (buying) execution the next trading day.

---

## 🛠️ Chartink Screener Conditions

Input these exact filters into Chartink in the Cash segment:

```text
Stock passes all of the below filters in cash segment:

1. [ ] Market Cap Greater than Number 5000
2. [ ] Daily Close Greater than Number 100
3. [ ] Daily Close Greater than equal to Daily Ema( Daily Close, 20 )
4. [ ] Daily Close Greater than equal to Daily Ema( Daily Close, 50 )
5. [ ] Daily Rsi( 14 ) Greater than equal to Number 50
6. [ ] Daily Rsi( 14 ) Less than equal to Number 65
7. [ ] Daily Close Greater than Daily Open
8. [ ] Daily Volume Greater than Daily Sma( Daily Volume, 20 )
9. [ ] Daily Volume Greater than 1 day ago Volume
```

### ⚡ Optional Filter: Relative Strength (vs Nifty 50)
Add this filter if you want to restrict the list strictly to market leaders on heavy volume days:
```text
Latest ( Close / Nifty 50 Close ) Greater than Latest Ema( ( Close / Nifty 50 Close ) , 20 )
```

---

## 📈 Quantitative Rationale

* **RSI Sweet Spot (50 to 65)**: Captures the acceleration phase of a daily trend before retail FOMO forces it into extreme overbought territory (greater than or equal to 70).
* **EMA 20 & 50 Confluence**: Ensures alignment with the primary medium-term structural uptrend.
* **Double Volume Surge**: Accelerating volume confirms institutional block-accumulation (smart money sweeps).
* **Liquidity Filter**: Eliminates illiquid penny stocks and limits slippage during fast executions.

---

## ⏱️ Execution Guide (Intraday Rules)

### 1. Opening Gate (Avoid the Gap Trap)
* **Rule**: **Do NOT market-buy the open.** Stocks closing strong often gap up. Buying the immediate open exposes you to morning mean-reversion pullbacks.
* **Wait**: Let the market print its first **15-minute candle** (9:15 AM - 9:30 AM).

### 2. The Entry Gate (Opening Range Breakout - ORB)
* Once the 15-minute range is established:
  * **Trigger**: Buy when the price breaks above the high of the first 15-minute candle.
  * **Volume Confirmation**: The breakout candle must show expanding volume compared to average 1-minute volumes.
  * **VWAP Rule**: Ensure the stock is trading strictly **above its intraday VWAP**.

### 3. Risk Management & Stop Loss
* **Stop Loss (SL)**: Place the SL at the **low of the 15-minute opening candle**, or at the intraday low if the stock has pulled back to VWAP and bounced.
* **Target**: Target a minimum of **1:1.5 or 1:2 Risk-to-Reward (R:R)**.
* **Time Exit**: If the target is not reached, **square off all positions automatically at 3:15 PM** to avoid overnight gap risk.
