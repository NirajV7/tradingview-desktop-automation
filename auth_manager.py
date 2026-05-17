import os
import json
import base64
from datetime import datetime
from fyers_apiv3 import fyersModel
from config import TOKEN_FILE, CLIENT_ID, SECRET_KEY, REDIRECT_URL

def check_auth():
    """Validates local Fyers token. Returns (needs_login, auth_url)."""
    def get_new_url():
        session = fyersModel.SessionModel(
            client_id=CLIENT_ID, secret_key=SECRET_KEY, redirect_uri=REDIRECT_URL,
            response_type="code", grant_type="authorization_code"
        )
        return session.generate_authcode()

    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            try:
                token_data = json.load(f)
                # 1. Check Date
                if token_data.get("date") != datetime.now().strftime("%Y-%m-%d"):
                    return True, get_new_url()
                
                # 2. Check JWT Expiry
                token = token_data.get("access_token", "")
                if token:
                    parts = token.split('.')
                    if len(parts) >= 2:
                        payload_b64 = parts[1]
                        payload_b64 += '=' * (-len(payload_b64) % 4)
                        payload_data = json.loads(base64.b64decode(payload_b64).decode('utf-8'))
                        exp = payload_data.get('exp')
                        if exp and datetime.now().timestamp() > exp:
                            return True, get_new_url()
                
                return False, None
            except Exception as e:
                print(f"Auth Check Error: {e}")
                return True, get_new_url()
    
    return True, get_new_url()

def exchange_token(auth_code):
    """Exchanges an authorization code for an access token and caches it."""
    if not auth_code:
        return False, "Auth code cannot be empty"
        
    if "auth_code=" in auth_code:
        auth_code = auth_code.split("auth_code=")[1].split("&")[0]
    
    try:
        session = fyersModel.SessionModel(
            client_id=CLIENT_ID, secret_key=SECRET_KEY, redirect_uri=REDIRECT_URL,
            response_type="code", grant_type="authorization_code"
        )
        session.set_token(auth_code)
        response = session.generate_token()
        
        if response.get("s") == "ok":
            access_token = response.get("access_token")
            with open(TOKEN_FILE, "w") as f:
                json.dump({
                    "access_token": access_token, 
                    "date": datetime.now().strftime("%Y-%m-%d")
                }, f)
            return True, "Authorized Successfully!"
        return False, response.get("message", "Failed to generate token")
    except Exception as e:
        return False, f"Exception during token exchange: {str(e)}"
