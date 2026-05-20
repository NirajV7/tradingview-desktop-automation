import csv
import re

def clean_number(val):
    if not val:
        return 0.0
    # Remove any non-numeric characters except dots and minus signs
    cleaned = re.sub(r'[^\d.-]', '', val)
    return float(cleaned) if cleaned else 0.0

def parse_percentage(val):
    if not val:
        return 0.0
    return float(val.replace('%', '').strip())

stocks = []
file_path = '/Users/nj/.gemini/antigravity/scratch/trading-automation/data/selected_stocks/MAY_20_BUY_STOCKS.csv'

with open(file_path, 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        # Check keys
        name = row.get('Stock Name', '')
        symbol = row.get('Symbol', '')
        close = clean_number(row.get('close', '0'))
        pct_change = parse_percentage(row.get('%_change', '0'))
        volume = clean_number(row.get('volume', '0'))
        
        # Calculate Turnover (Rupee Volume) in Lakhs/Crores
        turnover_inr = close * volume
        turnover_crores = turnover_inr / 10_000_000.0
        
        stocks.append({
            'name': name,
            'symbol': symbol,
            'close': close,
            'pct_change': pct_change,
            'volume': volume,
            'turnover_crores': turnover_crores
        })

# Sort by % Change descending
stocks_by_change = sorted(stocks, key=lambda x: x['pct_change'], reverse=True)

# Sort by Turnover (liquidity) descending
stocks_by_turnover = sorted(stocks, key=lambda x: x['turnover_crores'], reverse=True)

print("--- TOP 10 BY % CHANGE ---")
for i, s in enumerate(stocks_by_change[:10], 1):
    print(f"{i}. {s['symbol']} ({s['name']}): Close: {s['close']}, Change: {s['pct_change']}%, Vol: {s['volume']:,.0f}, Turnover: ₹{s['turnover_crores']:.2f} Cr")

print("\n--- TOP 10 BY TURNOVER (LIQUIDITY) ---")
for i, s in enumerate(stocks_by_turnover[:10], 1):
    print(f"{i}. {s['symbol']} ({s['name']}): Close: {s['close']}, Change: {s['pct_change']}%, Vol: {s['volume']:,.0f}, Turnover: ₹{s['turnover_crores']:.2f} Cr")

# Let's find high relative volume & price momentum candidates.
# High momentum breakout candidate: %_change > 3% and Turnover > 10 Crores
print("\n--- HIGH-CONVICTION BREAKOUT CANDIDATES (Change > 3% & Turnover > ₹10 Cr) ---")
candidates = [s for s in stocks if s['pct_change'] >= 3.0 and s['turnover_crores'] >= 10.0]
candidates_sorted = sorted(candidates, key=lambda x: x['pct_change'], reverse=True)
for i, s in enumerate(candidates_sorted, 1):
    print(f"{i}. {s['symbol']} ({s['name']}): Close: {s['close']}, Change: {s['pct_change']}%, Vol: {s['volume']:,.0f}, Turnover: ₹{s['turnover_crores']:.2f} Cr")
