import os
import csv
from dotenv import load_dotenv

# Load environment variables from .env in workspace CWD
CWD = "/Users/nj/.gemini/antigravity/scratch/trading-automation/"
load_dotenv(dotenv_path=os.path.join(CWD, ".env"))

TOKEN_FILE = os.path.join(CWD, "fyers_token.json")
WATCHLIST_FILE = os.path.join(CWD, "watchlist.json")
MASTER_CSV = os.path.join(CWD, "fyers_nse_cm.csv")
VENV_PYTHON = os.path.join(CWD, "venv/bin/python3")
CDP_URL = "http://localhost:9222/json"
TRADING_LOG = os.path.join(CWD, "trading_log.csv")
TRADING_LOG_5M = os.path.join(CWD, "trading_log_5m.csv")
TRADING_LOG_15M = os.path.join(CWD, "trading_log_15m.csv")
FYERS_LOG = os.path.join(CWD, "fyers_official_log.csv")
FYERS_LOG_5M = os.path.join(CWD, "fyers_log_5m.csv")
FYERS_LOG_15M = os.path.join(CWD, "fyers_log_15m.csv")
ENGINE_LOG = os.path.join(CWD, "engine.log")

CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
REDIRECT_URL = os.getenv("FYERS_REDIRECT_URL")

# Load Master Symbols for Search
MASTER_SYMBOLS = []
if os.path.exists(MASTER_CSV):
    with open(MASTER_CSV, 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) > 13:
                # Name, FyersSymbol, Ticker
                MASTER_SYMBOLS.append({
                    "name": row[1],
                    "fyers": row[9],
                    "ticker": row[13]
                })
