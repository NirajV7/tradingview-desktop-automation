import os
import csv
from dotenv import load_dotenv

# Load environment variables from .env in workspace CWD
CWD = "/Users/nj/.gemini/antigravity/scratch/trading-automation/"
load_dotenv(dotenv_path=os.path.join(CWD, ".env"))

TOKEN_FILE = os.path.join(CWD, "data", "fyers_token.json")
WATCHLIST_FILE = os.path.join(CWD, "data", "watchlist.json")
MASTER_CSV = os.path.join(CWD, "data", "fyers_nse_cm.csv")
VENV_PYTHON = os.path.join(CWD, "venv/bin/python3")
CDP_URL = "http://localhost:9222/json"
TRADING_LOG = os.path.join(CWD, "logs", "trading_log.csv")
TRADING_LOG_5M = os.path.join(CWD, "logs", "trading_log_5m.csv")
TRADING_LOG_15M = os.path.join(CWD, "logs", "trading_log_15m.csv")
FYERS_LOG = os.path.join(CWD, "logs", "fyers_official_log.csv")
FYERS_LOG_5M = os.path.join(CWD, "logs", "fyers_log_5m.csv")
FYERS_LOG_15M = os.path.join(CWD, "logs", "fyers_log_15m.csv")
FYERS_INDICATORS_5M = os.path.join(CWD, "logs", "fyers_indicators_5m.csv")
FYERS_INDICATORS_15M = os.path.join(CWD, "logs", "fyers_indicators_15m.csv")
ENGINE_LOG = os.path.join(CWD, "logs", "engine.log")
NIFTY_FEED_CSV = os.path.join(CWD, "logs", "nifty_50_feed.csv")
NIFTY_SPIKES_LOG = os.path.join(CWD, "logs", "nifty_spikes.log")

# Nifty 50 Stock Universe Tickers for Volumetric Radar
NIFTY_50_TICKERS = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", 
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BPCL", "BHARTIARTL", 
    "BRITANNIA", "CIPLA", "COALINDIA", "DIVISLAB", "DRREDDY", 
    "EICHERMOT", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", 
    "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "ITC", 
    "INDUSINDBK", "INFY", "JSWSTEEL", "KOTAKBANK", "LTM", 
    "LT", "M&M", "MARUTI", "NTPC", "NESTLEIND", 
    "ONGC", "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", 
    "SUNPHARMA", "TCS", "TATACONSUM", "TMCV", "TATASTEEL", 
    "TECHM", "TITAN", "ULTRACEMCO", "UPL", "WIPRO"
]
NIFTY_SYMBOLS = [f"NSE:{t}-EQ" for t in NIFTY_50_TICKERS]


CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
REDIRECT_URL = os.getenv("FYERS_REDIRECT_URL")

KITE_TOKEN_FILE = os.path.join(CWD, "data", "kite_token.json")
KITE_API_KEY = os.getenv("KITE_API_KEY")
KITE_API_SECRET = os.getenv("KITE_API_SECRET")
KITE_REDIRECT_URL = os.getenv("KITE_REDIRECT_URL", "http://127.0.0.1:8000/kite_auth")

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
