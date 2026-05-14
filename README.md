# NJ Quant Automation Suite 🚀

A high-performance trading automation system combining **TradingView** technicals with **Fyers** order flow data, all controlled via a unified **Web Dashboard**.

## 🖥️ The Web Dashboard
Everything is controlled through a local web interface running at `http://localhost:8080`.
- **Live Monitor**: Auto-refreshing view of Price, Volume, and Order Book depth.
- **Engine Controls**: Start/Stop TradingView and Fyers loggers with one click.
- **Auth Center**: Integrated Fyers API login flow. No terminal input required.

## 🌅 Daily Workflow
1. **Launch**: Double-click `Open_Trading_Dashboard.command` on your Desktop.
2. **Authorize**: Check the "Fyers API Authorization" card at the bottom. If red, click "Get Login Code" and paste the code back into the dashboard.
3. **Start Enginess**: 
   - Click **1. Open TradingView** (Chart Data).
   - Click **2. Start Fyers Engine** (Order Book).
   - Click **3. Start TV Logs** (Technical Indicators).

## 🛠️ Components
- `dashboard_app.py`: The Flask-based web server and control center.
- `fyers_official_logger.py`: Official Fyers v3 API bridge for market depth.
- `fetch_price.py`: CDP-based scraper for TradingView technical indicators.
- `fyers_official_log.csv`: High-resolution market flow data.
- `trading_log.csv`: Technical indicator history.

## 🔧 Maintenance
- **Stop All**: Click the red button in the dashboard to kill all background loggers.
- **Port Conflict**: Dashboard runs on port `8080` to avoid conflicts with macOS services.
