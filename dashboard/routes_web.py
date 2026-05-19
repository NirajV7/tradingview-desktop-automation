from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import os
import json
import config
import auth_manager
import kite_auth_manager
from dashboard.utils import load_watchlist
from urllib.parse import quote_plus

router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(config.CWD, "templates"))

@router.get("/", response_class=HTMLResponse)
async def index(request: Request, msg: str = None, msg_type: str = "success"):
    needs_login, auth_url = auth_manager.check_auth()
    kite_needs_login, kite_auth_url = kite_auth_manager.check_kite_auth()
    watchlist = load_watchlist()
    
    buy_symbols = watchlist.get("buy", [])
    sell_symbols = watchlist.get("sell", [])
    symbols_list = buy_symbols + sell_symbols
    
    current_symbols_text = ", ".join([s.split(":")[1].split("-")[0] if ":" in s else s for s in symbols_list])
    
    kite_margin = None
    if not kite_needs_login:
        kite_margin = kite_auth_manager.get_kite_margin()
        
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request, 
            "needs_login": needs_login, 
            "auth_url": auth_url,
            "kite_needs_login": kite_needs_login,
            "kite_auth_url": kite_auth_url,
            "kite_margin": kite_margin,
            "buy_symbols": buy_symbols,
            "sell_symbols": sell_symbols,
            "current_symbols": current_symbols_text,
            "msg": msg,
            "msg_type": msg_type
        }
    )

@router.post("/auth")
async def auth(auth_code: str = Form(...)):
    success, message = auth_manager.exchange_token(auth_code.strip())
    if success:
        return RedirectResponse(url="/?msg=Authorized+Successfully&msg_type=success", status_code=303)
    else:
        return RedirectResponse(url=f"/?msg={quote_plus(message)}&msg_type=error", status_code=303)

@router.get("/kite_auth")
async def kite_auth(request_token: str = None):
    if not request_token:
        return RedirectResponse(url="/?msg=No+request+token+received&msg_type=error", status_code=303)
    success, message = kite_auth_manager.exchange_kite_token(request_token.strip())
    if success:
        return RedirectResponse(url="/?msg=Kite+Authorized+Successfully&msg_type=success", status_code=303)
    else:
        return RedirectResponse(url=f"/?msg={quote_plus(message)}&msg_type=error", status_code=303)

@router.post("/kite_auth")
async def kite_auth_post(request_token_input: str = Form(...)):
    token = request_token_input.strip()
    if "request_token=" in token:
        try:
            token = token.split("request_token=")[1].split("&")[0]
        except Exception:
            pass
            
    success, message = kite_auth_manager.exchange_kite_token(token)
    if success:
        return RedirectResponse(url="/?msg=Kite+Authorized+Successfully&msg_type=success", status_code=303)
    else:
        return RedirectResponse(url=f"/?msg={quote_plus(message)}&msg_type=error", status_code=303)

@router.get("/clear_watchlist")
async def clear_watchlist(direction: str = None):
    watchlist = load_watchlist()
    if direction in ['buy', 'sell']:
        watchlist[direction] = []
        msg = f"{direction.upper()} Watchlist Cleared"
    else:
        watchlist = {"buy": [], "sell": []}
        msg = "All Watchlists Cleared"
        
    with open(config.WATCHLIST_FILE, "w") as f:
        json.dump(watchlist, f)
    return RedirectResponse(url=f"/?msg={quote_plus(msg)}&msg_type=success", status_code=303)
