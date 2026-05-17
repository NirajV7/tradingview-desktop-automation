# Implementation Plan - Dynamic Asynchronous Control Switching

We are upgrading NJ's Quant Mission Control engine controls sidebar. Instead of static, hard-reloading hyperlinks, we will build a sleek, asynchronous non-reloading toggle system for starting and stopping individual engines, alongside a master Start/Stop-All controller.

## Proposed Changes

We will unify both backend frameworks (FastAPI and Flask) to serve the exact same premium stylesheet and layout template (`templates/index.html`), ensuring absolute synchrony and removing extensive code duplication.

---

### 1. Frontend Enhancements

#### [MODIFY] [index.html](file:///Users/nj/.gemini/antigravity/scratch/trading-automation/templates/index.html)
* **Dynamic Master Controller**:
  * Enhance the JavaScript `updateStatus()` function to automatically monitor individual engine states.
  * Dynamically disable `⚡ START ALL` if all engines are already operational.
  * Dynamically disable `🛑 STOP ALL` if all engines are completely stopped.
  * Use fluid opacity reductions to provide immediate visual feedback.

---

### 2. Backend Enhancements

#### [MODIFY] [dashboard_app.py](file:///Users/nj/.gemini/antigravity/scratch/trading-automation/dashboard_app.py)
* **Unification of Layout Templates**:
  * Replace Flask's legacy `render_template_string(HTML_TEMPLATE, ...)` with native `render_template("index.html", ...)` to consume the same beautiful glassmorphic layout file.
  * Completely delete the massive duplicate 330-line `HTML_TEMPLATE` variable string.
* **Notification System Synchronization**:
  * Refactor Flask redirects (`flash()`) inside all engine control, log wiping, and watchlist synchronization endpoints to redirect using standard query parameters (`?msg=...&msg_type=...`).
  * This matches FastAPI's architecture and allows `index.html`'s JavaScript query string parser to automatically show beautiful toast notifications seamlessly under both engines.

---

### 3. Verification Plan

#### Automated Verification
1. Run local syntax checks to verify Python file hygiene:
   ```bash
   python3 -m py_compile fastapi_app.py dashboard_app.py
   ```

#### Manual Verification
1. Ask the Principal to launch either `fastapi_app.py` or `dashboard_app.py` locally.
2. Manually test button transitions, verifying state switches from normal colored outlines to red active states upon execution without full page refreshes.
3. Verify that toast notifications appear beautifully at the top-right corner whenever engines are started, stopped, or synchronized.
