# 🚀 NJ Quant Terminal: Mission Control

An institutional-grade trading automation suite designed for high-precision trend following. This terminal bridges **TradingView Desktop** and the **Fyers v3 API** into a unified, real-time, low-latency decision-making dashboard.

## 📈 Core Intelligence: Trend Confirmation
The terminal's primary feature is the **Dual-Timeframe Trend Confirmation Engine**.
- **The Wave (5m)**: Real-time price action vs. VWAP on the 5-minute interval.
- **The Tide (15m)**: Structural trend confirmation on the 15-minute interval.
- **Dynamic Trend Evaluation**:
  * 🟢 **BULLISH**: Price > VWAP, 20 EMA > 50 EMA, Price > 200 EMA, and RSI > 50 (momentum confirmed).
  * 🔴 **BEARISH**: Price < VWAP, 20 EMA < 50 EMA, Price < 200 EMA, and RSI < 50 (breakdown confirmed).
  * ⚠️ **OVERBOUGHT / OVERSOLD**: Extreme RSI readings (>70 or <30) flagging chase warnings.
  * 🟡 **CONGESTION**: Sideways or conflicting signals.

## 🛠️ Key Features
- **ASGI/FastAPI Backend**: Microsecond-latency non-blocking I/O handling asynchronous telemetry streaming.
- **Premium Glassmorphic UI**: High-contrast, dark mode controls designed for active trading desks.
- **Dynamic Asynchronous Controls**: Toggle components (Fyers, Loggers, Scrapers) on/off instantly without page reloads.
- **Decoupled TradingView App**: Standalone chart integration that remains open for macro analysis while backend loggers start and stop.
- **Heartbeat Status LEDs**: Real-time polling monitoring active background processes.

## 📁 Modular Technical Architecture
The codebase has been refactored for strict separation of concerns:
* **[dashboard_app.py](file:///Users/nj/.gemini/antigravity/scratch/trading-automation/dashboard_app.py)**: Async FastAPI ASGI web application controller.
* **[config.py](file:///Users/nj/.gemini/antigravity/scratch/trading-automation/config.py)**: Consolidates environment configs, token files, and symbol masters.
* **[sys_ops.py](file:///Users/nj/.gemini/antigravity/scratch/trading-automation/sys_ops.py)**: OS-level subprocess handlers, process tracking (`pgrep`), and TradingView CDP interrogator.
* **[auth_manager.py](file:///Users/nj/.gemini/antigravity/scratch/trading-automation/auth_manager.py)**: Handles cryptographically secure token decryption, expiry checks, and OAuth exchange.
* **[fetch_price.py](file:///Users/nj/.gemini/antigravity/scratch/trading-automation/fetch_price.py)**: Chrome DevTools Protocol (CDP) technical indicators scraper.
* **[fyers_official_logger.py](file:///Users/nj/.gemini/antigravity/scratch/trading-automation/fyers_official_logger.py)**: High-speed websocket consumer for real-time Fyers data.
* **`templates/index.html`**: Premium non-reloading glassmorphic visual front-end dashboard.
* **`static/css/style.css`**: Institutional-grade typography, glowing indicators, and transitions.

## 🌅 The NJ Workflow
1. **Launch Control Center**: Start the unbuffered ASGI web server on port `8080`:
   ```bash
   ./venv/bin/python3 dashboard_app.py
   ```
2. **Synchronize Workspace**:
   * Click **[ OPEN ]** in the TradingView App row to launch or verify your chart environment.
   * Add active watchlists and click **[ SYNC TABS ]** to populate chart intervals automatically.
3. **Engage Engines**:
   * Click **`⚡ START ALL`** (or individual start toggles) to kick off Fyers WebSocket logs and TV Price Scrapers.
4. **Halt Safely**:
   * Click **`🛑 STOP ALL`** to terminate backend collection engines cleanly. Desktop TradingView remains untouched.

---
*Built for Niraj (NJ) | Bengaluru, India | Capital Preservation First.* 🛡️
