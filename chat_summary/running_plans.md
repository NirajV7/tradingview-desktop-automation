# Modularizing the Zerodha Kite Execution Engine

We will split the monolithic ~1,130-line `trade_setup/kite_execution_engine.py` into a package of clean, single-responsibility sub-modules under a new folder `trade_setup/engine/`.

## Core Guidelines
- The core code, business logic, rules evaluation logic, and math calculations will remain **100% identical** to preserve performance and prevent any runtime behavior drift.
- The modular components will be attached directly to the `KiteExecutionEngine` class using standard Python class-level delegate binding. This ensures all method calls, `self` scoping, and state references continue to work seamlessly.

## Proposed Layout

### 📁 New Engine Subdirectory: `trade_setup/engine/`

#### 1. `__init__.py`
* Empty initialization script marking `engine/` as a Python package.

#### 2. `telemetry.py`
* Encapsulates log reading and volume/ORB metrics calculations.
* Methods: `get_orb_range_from_logs`, `get_volume_baseline`, `get_volume_baseline_15m`, `get_tick_spread_volume`, `get_daily_open_price`.

#### 3. `costs.py`
* Encapsulates transaction fee computations for Zerodha MIS orders.
* Methods: `fetch_transaction_costs`.

#### 4. `journal.py`
* Handles automated trade logging and ledger updates in `trade_journal.md`.
* Methods: `log_trade_to_journal`.

#### 5. `rules.py`
* Manages ORB breakout strategy entry gates.
* Methods: `evaluate_live_rules`.

#### 6. `risk.py`
* Enforces ₹2,500 max risk sizing, exposure thresholds, and margin verification.
* Methods: `execute_order_disciplines`.

#### 7. `orders.py`
* Integrates Kite bracket orders and transaction execution logic.
* Methods: `place_kite_bracket_defense`.

#### 8. `auditor.py`
* Manages trailing stops, target achievements, and active trade monitoring.
* Methods: `audit_active_trades`.

---

### ⚙️ Engine Orchestrator: `trade_setup/kite_execution_engine.py`
* Clean up the core orchestrator script, removing the extracted method definitions and importing them from `engine/` package to bind them to the class.
```python
# Import delegated methods
from engine.telemetry import get_orb_range_from_logs, get_volume_baseline, get_volume_baseline_15m, get_tick_spread_volume, get_daily_open_price
from engine.costs import fetch_transaction_costs
from engine.journal import log_trade_to_journal
from engine.rules import evaluate_live_rules
from engine.risk import execute_order_disciplines
from engine.orders import place_kite_bracket_defense
from engine.auditor import audit_active_trades

class KiteExecutionEngine:
    # Core initialization and polling loop logic remains here
    
    # Class-level delegates
    get_orb_range_from_logs = get_orb_range_from_logs
    get_volume_baseline = get_volume_baseline
    get_volume_baseline_15m = get_volume_baseline_15m
    get_tick_spread_volume = get_tick_spread_volume
    get_daily_open_price = get_daily_open_price
    
    fetch_transaction_costs = fetch_transaction_costs
    log_trade_to_journal = log_trade_to_journal
    evaluate_live_rules = evaluate_live_rules
    execute_order_disciplines = execute_order_disciplines
    place_kite_bracket_defense = place_kite_bracket_defense
    audit_active_trades = audit_active_trades
```
