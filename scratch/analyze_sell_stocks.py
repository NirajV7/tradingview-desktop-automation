import csv
import re

def clean_number(val):
    if not val:
        return 0.0
    cleaned = re.sub(r'[^\d.-]', '', val)
    return float(cleaned) if cleaned else 0.0

def parse_percentage(val):
    if not val:
        return 0.0
    return float(val.replace('%', '').strip())

stocks = []
file_path = '/Users/nj/.gemini/antigravity/scratch/trading-automation/data/selected_stocks/MAY_20_SELL_STOCKS.csv'

with open(file_path, 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        name = row.get('Stock Name', '')
        symbol = row.get('Symbol', '')
        close = clean_number(row.get('close', '0'))
        pct_change = parse_percentage(row.get('%_change', '0'))
        volume = clean_number(row.get('volume', '0'))
        
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

# Sort by % Change ascending (most negative first)
stocks_by_change = sorted(stocks, key=lambda x: x['pct_change'])

# Sort by Turnover (liquidity) descending
stocks_by_turnover = sorted(stocks, key=lambda x: x['turnover_crores'], reverse=True)

print("--- TOP 10 BY % CHANGE (MOST NEGATIVE) ---")
for i, s in enumerate(stocks_by_change[:10], 1):
    print(f"{i}. {s['symbol']} ({s['name']}): Close: {s['close']}, Change: {s['pct_change']}%, Vol: {s['volume']:,.0f}, Turnover: ₹{s['turnover_crores']:.2f} Cr")

print("\n--- TOP 10 BY TURNOVER (LIQUIDITY) ---")
for i, s in enumerate(stocks_by_turnover[:10], 1):
    print(f"{i}. {s['symbol']} ({s['name']}): Close: {s['close']}, Change: {s['pct_change']}%, Vol: {s['volume']:,.0f}, Turnover: ₹{s['turnover_crores']:.2f} Cr")

# High-conviction short candidates: %_change < -0.5% and Turnover > 10 Crores
print("\n--- HIGH-CONVICTION SHORT CANDIDATES (Change < -0.5% & Turnover > ₹10 Cr) ---")
candidates = [s for s in stocks if s['pct_change'] <= -0.5 and s['turnover_crores'] >= 10.0]
candidates_sorted = sorted(candidates, key=lambda x: x['pct_change'])
for i, s in enumerate(candidates_sorted, 1):
    print(f"{i}. {s['symbol']} ({s['name']}): Close: {s['close']}, Change: {s['pct_change']}%, Vol: {s['volume']:,.0f}, Turnover: ₹{s['turnover_crores']:.2f} Cr")
