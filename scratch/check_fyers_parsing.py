import csv
import os
import sys
sys.path.append("/Users/nj/.gemini/antigravity/scratch/trading-automation")
import config

if __name__ == "__main__":
    fyers_ltp = {}
    if os.path.exists(config.FYERS_LOG):
        try:
            with open(config.FYERS_LOG, "r") as f:
                lines = f.readlines()
                if len(lines) > 1:
                    reader = csv.DictReader(lines)
                    for row in reader:
                        sym = row.get('symbol', '')
                        name = sym.split(":")[1].split("-")[0] if ":" in sym else sym
                        lp_val = row.get('last_price')
                        if lp_val and lp_val != '...':
                            try:
                                fyers_ltp[name] = float(lp_val)
                            except ValueError:
                                pass
        except Exception as e:
            print(f"Error: {e}")
            
    print("Parsed fyers_ltp dict:")
    print(fyers_ltp)
