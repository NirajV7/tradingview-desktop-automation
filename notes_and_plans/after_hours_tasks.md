# 📝 After-Hours System Fix Tasks

## 1. Issue: Subprocess Output Buffering & Dashboard Console Lag
* **Problem**: When starting `kite_execution_engine.py`, `fyers_official_logger.py`, or `nifty_radar.py` through the Web Dashboard UI buttons, the console output lag is extremely high (often updates take minutes or never appear).
* **Technical Cause**: Python standard output (`stdout`) buffers output by default when piped or redirected into log files like `engine.log`. Furthermore, modifying `dashboard_app.py` to add the `-u` (unbuffered) flag did not take effect because the FastAPI application is already running in memory and cannot reload without stopping the trading session.
* **Fix Applied So Far**: The command list in `dashboard_app.py` has been updated with `-u` for all processes.
* **Remaining Action**: 
  * After 3:30 PM IST (market close), safely restart the dashboard server to load the new command lists into memory.
  * Command to restart:
    ```bash
    pkill -f dashboard_app.py
    nohup venv/bin/python3 dashboard_app.py >> fastapi.log 2>&1 &
    ```

## 2. Enhancement: Remove Cleanup Script from Dashboard Shutdown
* **Problem**: Currently, when the FastAPI dashboard server `dashboard_app.py` is stopped or restarted, it automatically triggers a hard-coded cleanup block that kills all background engines:
  ```python
  sys_ops.stop_process("nifty_radar.py")
  subprocess.run("pkill -f kite_execution_engine.py", shell=True)
  ```
  This is a critical risk if we ever want to restart the dashboard server during active trading without killing the trading engines.
* **After-Hours Fix Plan**:
  * Edit the `if __name__ == "__main__":` block at the bottom of `dashboard_app.py`.
  * Make this cleanup routine *optional* or remove it so the engines can run independently even if the dashboard UI restarts.

## 3. Architecture Proposal: Nifty Momentum Spiker Integration
* **Objective**: Leverage passive institutional flow alerts from `nifty_radar.py` to trigger automated actions.
* **Option A: Dynamic Watchlist rotation**
  * When a Nifty 50 stock crosses the "Radar Confidence Gate" (Volume > 5x, Price Delta > 0.4%, ATR > 1.5%), automatically append it to `watchlist.json` in real-time.
  * The Kite Execution Engine will dynamically load the new symbol on its next loop, lock the ORB range, and evaluate setups.
* **Option B: Broad Market Breadth Guard**
  * Use a rolling 15-minute buying/selling ratio on Nifty 50 spikers to calculate global market sentiment.
  * Halt new long entries or scale down size if the selling spike ratio is dominant, blocking buy traps during a flash dump.
* **Option C: High-Volume "Spike & Pullback" Strategy**
  * Monitor stocks that register a massive volume spike, wait for them to pull back to the 5m EMA20/VWAP with low volume and a cooled RSI (50-60), and buy the touchback with a tight stop below the spike candle low.

