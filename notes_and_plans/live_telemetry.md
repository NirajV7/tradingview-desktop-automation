============================================================
📊 LIVE TELEMETRY CONTEXT BRIDGE (Fyers + TradingView)
Generated at: 2026-05-19 05:41:46 IST
============================================================

### 1. MICRO-VELOCITY ORDER FLOW (Last 8 Ticks / 1 Min)

#### [1A. Fyers Level-1 Micro Ticks (5s Frequency)]
| Ticker | Last Price (LTP) | Spread Buy Qty | Spread Sell Qty | Cumulative Vol | Last Tick time |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **APOLLO** | [ No ticks logged ] | - | - | - | - |
| **HINDCOPPER** | [ No ticks logged ] | - | - | - | - |
| **INDUSTOWER** | [ No ticks logged ] | - | - | - | - |
| **KMEW** | [ No ticks logged ] | - | - | - | - |
| **RATEGAIN** | [ No ticks logged ] | - | - | - | - |

### 2. 5-MINUTE WAVE PROGRESSION (Last 10 Closed 5M Candles)

#### [2A. Fyers 5-Minute Volume & Spread Progression]
| Ticker | LTP | Spread Buy Qty | Spread Sell Qty | Cumulative Vol | Time |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **APOLLO** | [ No ticks logged ] | - | - | - | - |
| **HINDCOPPER** | [ No ticks logged ] | - | - | - | - |
| **INDUSTOWER** | [ No ticks logged ] | - | - | - | - |
| **KMEW** | [ No ticks logged ] | - | - | - | - |
| **RATEGAIN** | [ No ticks logged ] | - | - | - | - |

### 3. 15-MINUTE MACRO TIDE PROGRESSION (Last 10 Closed 15M Candles)

#### [3A. Fyers 15-Minute Volume & Spread Progression]
| Ticker | LTP | Spread Buy Qty | Spread Sell Qty | Cumulative Vol | Time |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **APOLLO** | [ No ticks logged ] | - | - | - | - |
| **HINDCOPPER** | [ No ticks logged ] | - | - | - | - |
| **INDUSTOWER** | [ No ticks logged ] | - | - | - | - |
| **KMEW** | [ No ticks logged ] | - | - | - | - |
| **RATEGAIN** | [ No ticks logged ] | - | - | - | - |
### 4. FYERS-BACKED TECHNICAL INDICATOR ENGINE (Real-Time Server Calculations)

#### [4A. Fyers 5-Minute Technical Candles (Calculated from Fyers API)]
| Ticker | Price | VWAP | Trend State | EMA(20) | EMA(50) | EMA(200) | RSI | ADR (%) | ADR (Abs) | Time |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **APOLLO** | 320.00 | 302.35 | ⚠️ OVERBOUGHT | 298.48 | 293.45 | 293.80 | 83.97 | 5.79% | ₹17.12 | 15:25:00 |
| **HINDCOPPER** | 580.50 | 582.16 | 🟡 CONGESTION | 579.87 | 580.19 | 584.24 | 53.02 | 3.46% | ₹19.29 | 15:25:00 |
| **INDUSTOWER** | 431.95 | 430.03 | 🟢 BULLISH | 430.31 | 430.11 | 428.65 | 64.52 | 3.11% | ₹12.53 | 15:25:00 |
| **KMEW** | 2065.00 | 2076.67 | 🟡 CONGESTION | 2085.01 | 2086.02 | 2037.35 | 42.62 | 7.55% | ₹147.26 | 15:25:00 |
| **RATEGAIN** | 639.30 | 639.89 | 🟡 CONGESTION | 638.74 | 634.91 | 632.90 | 55.55 | 4.69% | ₹28.37 | 15:25:00 |

#### [4B. Fyers 15-Minute Technical Candles (Calculated from Fyers API)]
| Ticker | Price | VWAP | Trend State | EMA(20) | EMA(50) | EMA(200) | RSI | ADR (%) | ADR (Abs) | Time |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **APOLLO** | 320.00 | 301.30 | ⚠️ OVERBOUGHT | 293.41 | 292.66 | 300.00 | 79.89 | 5.79% | ₹17.12 | 15:15:00 |
| **HINDCOPPER** | 580.50 | 582.20 | 🟡 CONGESTION | 580.31 | 581.48 | 576.76 | 49.88 | 3.46% | ₹19.29 | 15:15:00 |
| **INDUSTOWER** | 431.95 | 429.94 | 🟢 BULLISH | 430.27 | 429.50 | 420.00 | 57.96 | 3.11% | ₹12.53 | 15:15:00 |
| **KMEW** | 2065.00 | 2076.95 | 🟡 CONGESTION | 2083.48 | 2060.15 | 2055.20 | 47.37 | 7.55% | ₹147.26 | 15:15:00 |
| **RATEGAIN** | 639.30 | 638.79 | 🟢 BULLISH | 634.42 | 632.65 | 629.61 | 58.01 | 4.69% | ₹28.37 | 15:15:00 |

============================================================
👉 INSTRUCTIONS FOR CLAUDE:
1. Map these indicators to your active positions queried via mcp_kite_get_positions().
2. Normalise symbol 'SBIN' with 'NSE:SBIN-EQ' (Fyers) / 'NSE:SBIN' (Zerodha).
3. CRITICAL QUANTITATIVE TREND CONFIRMATION ENGINE LOGIC:
   The 'Trend State' in the telemetry tables is evaluated using these strict rules:
   🟢 Bullish Setup (Breakout Confirmation):
     - Rule 1 (Baseline): Price > VWAP (Price is trading above institutional average price)
     - Rule 2 (Trend Structure): 20 EMA > 50 EMA (Short-term trend is above mid-term trend)
     - Rule 3 (Long-term Anchor): Price > 200 EMA (Overall macro structure is supportive)
     - Rule 4 (Momentum): RSI > 50 (Buying pressure is dominant)
   🔴 Bearish Setup (Breakdown Confirmation):
     - Rule 1 (Baseline): Price < VWAP (Price is trading below institutional average price)
     - Rule 2 (Trend Structure): 20 EMA < 50 EMA (Short-term trend is below mid-term trend)
     - Rule 3 (Long-term Anchor): Price < 200 EMA (Overall macro structure is resistive)
     - Rule 4 (Momentum): RSI < 50 (Selling pressure is dominant)
   Mapped Trend States in Telemetry Table:
     - 🟢 BULLISH: All 4 Bullish rules are met.
     - 🔴 BEARISH: All 4 Bearish rules are met.
     - ⚠️ OVERBOUGHT: All 4 Bullish rules are met, but RSI > 70 (caution on chase).
     - ⚠️ OVERSOLD: All 4 Bearish rules are met, but RSI < 30 (caution on shorting support).
     - 🟡 CONGESTION: Indicators are conflicting or sideways.
4. Actionable Directives:
   - When Trend State is 🟢 BULLISH: Look for long entries on pullbacks to the 20/50 EMAs.
   - When Trend State is 🔴 BEARISH: Look for short entries on rallies to the 20/50 EMAs.
   - When Trend State is 🟡 CONGESTION: Avoid starting new momentum trades (market is choppy).
   - When Trend State is ⚠️ OVERBOUGHT / ⚠️ OVERSOLD: Tighten trailing stops immediately.
============================================================
