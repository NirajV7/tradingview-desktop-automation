# TradingView Automation Workspace

This workspace contains a standalone Python system to fetch live data from the **TradingView Desktop** application.

## 🚀 The Main Script
- **`fetch_price.py`**: Run this to fetch live Price, RSI, EMAs, VWAP, and Timeframes from all open TradingView tabs.
  - **Run Command**: `./venv/bin/python3 fetch_price.py`

## 🛠 Developer / Debug Tools (Ignore these)
These scripts were used to "reverse engineer" the TradingView Desktop internal memory to find the correct data paths. You do not need to run them.
- `probe_tabs.py`: Found which tab contains the actual chart data.
- `get_frames.py`: Verified that the chart is not hidden inside an iframe.
- `probe_globals.py`: Discovered the `_exposed_chartWidgetCollection` variable.
- `find_value.py`: Located the exact memory address of the price value.
- `get_model_keys.py`: Explored the chart's internal programming model.
- `probe_studies.py`: Found the internal names for RSI and other indicators.

## ⚙️ Setup Requirements
1. **TradingView Desktop** must be open.
2. It must be running with the remote debugging port enabled (Port 9222).
3. The virtual environment must be active or used directly: `./venv/bin/python3`.
