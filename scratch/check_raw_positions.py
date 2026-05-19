import os
import sys
import json
sys.path.append("/Users/nj/.gemini/antigravity/scratch/trading-automation")
import kite_auth_manager

if __name__ == "__main__":
    if os.path.exists(kite_auth_manager.KITE_TOKEN_FILE):
        with open(kite_auth_manager.KITE_TOKEN_FILE, "r") as f:
            token_data = json.load(f)
            access_token = token_data.get("access_token")
            if access_token:
                from kiteconnect import KiteConnect
                kite = KiteConnect(api_key=kite_auth_manager.KITE_API_KEY)
                kite.set_access_token(access_token)
                positions = kite.positions()
                print("RAW NET POSITIONS:")
                print(json.dumps(positions.get("net", []), indent=2))
            else:
                print("Access token not found in token file.")
    else:
        print("Token file not found.")
