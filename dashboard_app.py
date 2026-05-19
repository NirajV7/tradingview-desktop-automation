from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import os
import asyncio
import subprocess
import uvicorn

import config
import sys_ops
from dashboard.cache import fyers_cache_updater

app = FastAPI(title="NJ Quant Terminal")

# Mount Static Files
app.mount("/static", StaticFiles(directory=os.path.join(config.CWD, "static")), name="static")

# Register Background Tasks
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(fyers_cache_updater())

# Import & Register APIRouters
from dashboard.routes_web import router as web_router
from dashboard.routes_system import router as system_router
from dashboard.routes_api import router as api_router
from dashboard.routes_kite import router as kite_router
from dashboard.routes_radar import router as radar_router

app.include_router(web_router)
app.include_router(system_router)
app.include_router(api_router)
app.include_router(kite_router)
app.include_router(radar_router)

if __name__ == "__main__":
    print("🧹 Cleaning up lingering background engines...")
    subprocess.run("pkill -f fyers_official_logger.py", shell=True)
    subprocess.run("pkill -f fetch_price.py", shell=True)
    sys_ops.stop_process("nifty_radar.py")
    subprocess.run("pkill -f kite_execution_engine.py", shell=True)
    
    # Launch uvicorn loop
    uvicorn.run("dashboard_app:app", host="127.0.0.1", port=8080, reload=True)
