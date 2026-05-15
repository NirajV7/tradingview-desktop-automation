# 🚀 NJ Quant Terminal: Mission Control

An institutional-grade trading automation suite designed for high-precision trend following. This terminal bridges **TradingView Desktop** and the **Fyers v3 API** into a unified, real-time decision-making dashboard.

## 📈 Core Intelligence: Trend Confirmation
The terminal's primary feature is the **Dual-Timeframe Trend Confirmation Engine**.
- **The Wave (5m)**: Real-time price action vs VWAP on the 5-minute interval.
- **The Tide (15m)**: Structural trend confirmation on the 15-minute interval.
- **Trend Signal**: The system automatically correlates both timeframes to generate definitive **BULLISH**, **BEARISH**, or **CONFLICT** signals.

## 🛠️ Key Features
- **Signal Grid**: A professional-grade table displaying synchronized price data across broker and chart.
- **One-Click Sync**: Automated CDP-based synchronization that opens 5m and 15m pairs for every stock in your watchlist.
- **Live Console**: Real-time observability of background engines with heartbeat monitoring and log rotation.
- **Smart Auth**: Zero-manual-work authentication flow for Fyers v3 API.
- **Ghost Protection**: Precision process management using `pgrep` to prevent background "phantom" processes.

## 🌅 The NJ Workflow
1. **Launch Dashboard**: Start `dashboard_app.py` to open the Control Center at `http://localhost:8080`.
2. **Sync Environment**:
   - Click **[ OPEN ]** to launch TradingView Desktop.
   - Click **[ SYNC TABS ]** to automatically populate your charts with 5m/15m pairs.
3. **Engage Engines**:
   - Start the **Fyers Engine** for official broker price and depth.
   - Start **TV Price Logs** for technical indicator streaming.
4. **Execute**: Monitor the **Trend Signal** for confirmation before taking entries.

## 📁 Technical Architecture
- `dashboard_app.py`: The Flask-based orchestration engine.
- `fetch_price.py`: CDP scraper for real-time technicals (VWAP, EMA, RSI).
- `fyers_official_logger.py`: High-frequency bridge to Fyers Market Data.
- `trading_log.csv`: Timeframe-indexed technical database.
- `engine.log`: Centralized system observability log.

---
*Built for Niraj (NJ) | Bengaluru, India | Capital Preservation First.* 🛡️
