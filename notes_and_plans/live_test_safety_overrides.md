# Live Testing Safety Overrides & Rollback Guide

This document logs the temporary changes applied for scaled-down live market testing. To revert the system to standard production configuration, restore the original values detailed below.

---

## 🔍 Modified Parameters & Code Blocks

### 1. Risk Per Trade (`self.risk_per_trade`)
* **File:** [kite_execution_engine.py](file:///Users/nj/.gemini/antigravity/scratch/trading-automation/trade_setup/kite_execution_engine.py)
* **Original State (Production):**
  ```python
  self.risk_per_trade = 2500.0  # Conservative risk limit per trade (₹)
  ```
* **Temporary State (Testing):**
  ```python
  self.risk_per_trade = 100.0  # Scaled down for live safety testing (₹)
  ```

---

### 2. Radar Daily Loss Limit Guard
* **File:** [risk.py](file:///Users/nj/.gemini/antigravity/scratch/trading-automation/trade_setup/engine/risk.py) inside `check_radar_daily_loss_limit`
* **Original State (Production):**
  ```python
      if total_loss >= 2000:
          print(f"⚠️  Daily Radar Loss Limit Hit: Realized loss is ₹{total_loss:.2f} (Limit: ₹2000)")
          return True
  ```
* **Temporary State (Testing):**
  ```python
      if total_loss >= 100:
          print(f"⚠️  Daily Radar Loss Limit Hit: Realized loss is ₹{total_loss:.2f} (Limit: ₹100)")
          return True
  ```

---

### 3. Sizing Quantity Floor (ORB Buy)
* **File:** [risk.py](file:///Users/nj/.gemini/antigravity/scratch/trading-automation/trade_setup/engine/risk.py) inside `execute_order_disciplines`
* **Original State (Production):**
  ```python
      quantity = int(self.risk_per_trade // sl_width)
      if quantity <= 0:
          print(f"❌ Sizing Error: Calculated quantity is 0 for {symbol}")
          return
  ```
* **Temporary State (Testing):**
  ```python
      quantity = int(self.risk_per_trade // sl_width)
      quantity = max(1, quantity)  # Safety floor for tiny test sizes
  ```

---

### 4. Sizing Quantity Floor (ORB Sell)
* **File:** [risk.py](file:///Users/nj/.gemini/antigravity/scratch/trading-automation/trade_setup/engine/risk.py) inside `execute_sell_order_disciplines`
* **Original State (Production):**
  ```python
      quantity = int(self.risk_per_trade // sl_width)
      if quantity <= 0:
          print(f"❌ Sizing Error: Calculated quantity is 0 for {symbol}")
          return
  ```
* **Temporary State (Testing):**
  ```python
      quantity = int(self.risk_per_trade // sl_width)
      quantity = max(1, quantity)  # Safety floor for tiny test sizes
  ```

---

### 5. Sizing Quantity Floor (Radar Pullback Buy)
* **File:** [risk.py](file:///Users/nj/.gemini/antigravity/scratch/trading-automation/trade_setup/engine/risk.py) inside `execute_radar_buy_disciplines`
* **Original State (Production):**
  ```python
      quantity = int(self.risk_per_trade // sl_width)
      if quantity <= 0:
          print(f"❌ Sizing Error: Calculated quantity is 0 for {symbol}")
          return
  ```
* **Temporary State (Testing):**
  ```python
      quantity = int(self.risk_per_trade // sl_width)
      quantity = max(1, quantity)  # Safety floor for tiny test sizes
  ```

---

### 6. Sizing Quantity Floor (Radar Pullback Sell)
* **File:** [risk.py](file:///Users/nj/.gemini/antigravity/scratch/trading-automation/trade_setup/engine/risk.py) inside `execute_radar_sell_disciplines`
* **Original State (Production):**
  ```python
      quantity = int(self.risk_per_trade // sl_width)
      if quantity <= 0:
          print(f"❌ Sizing Error: Calculated quantity is 0 for {symbol}")
          return
  ```
* **Temporary State (Testing):**
  ```python
      quantity = int(self.risk_per_trade // sl_width)
      quantity = max(1, quantity)  # Safety floor for tiny test sizes
  ```
