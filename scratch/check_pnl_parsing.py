import csv
from collections import deque

fyers_ltp = {}
with open("fyers_official_log.csv", "r") as f:
    header_line = f.readline().strip()
    if header_line:
        header = header_line.split(',')
        last_lines = deque(f, maxlen=300)
        reader = csv.DictReader(last_lines, fieldnames=header)
        for row in reader:
            sym = row.get('symbol', '')
            name = sym.split(":")[1].split("-")[0] if ":" in sym else sym
            lp_val = row.get('last_price')
            if lp_val and lp_val != '...':
                try:
                    fyers_ltp[name] = float(lp_val)
                except ValueError:
                    pass
print(fyers_ltp)
