import os
import csv
import json
import shutil
from datetime import datetime

# Setup paths
CWD = "/Users/nj/.gemini/antigravity/scratch/trading-automation/"
LOGS_DIR = os.path.join(CWD, "logs")
ARCHIVE_DIR = os.path.join(LOGS_DIR, "archive")
DATA_DIR = os.path.join(CWD, "data")

def rotate_and_clean():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    current_archive_dir = os.path.join(ARCHIVE_DIR, timestamp)
    os.makedirs(current_archive_dir, exist_ok=True)
    print(f"📦 Created archive directory: {current_archive_dir}")

    # List of files to rotate and clean
    csv_configs = {
        "fyers_log_5m.csv": 200,          # Keep last 200 rows per symbol
        "fyers_log_15m.csv": 100,         # Keep last 100 rows per symbol
        "fyers_indicators_5m.csv": 200,   # Keep last 200 rows per symbol
        "fyers_indicators_15m.csv": 100,  # Keep last 100 rows per symbol
        "fyers_official_log.csv": 500,    # Keep last 500 rows per symbol
        "nifty_50_feed.csv": 5000,        # Keep last 5000 rows total (for Radar)
    }

    log_files_to_truncate = [
        "dashboard.log",
        "engine.log",
        "fastapi.log",
        "fyers.log",
        "fyersApi.log",
        "fyersDataSocket.log",
        "fyersRequests.log",
        "nifty_spikes.log"
    ]

    # 1. Archive and process CSV files
    for filename, keep_count in csv_configs.items():
        file_path = os.path.join(LOGS_DIR, filename)
        if not os.path.exists(file_path):
            continue

        # Copy to archive
        shutil.copy(file_path, os.path.join(current_archive_dir, filename))
        
        # Read and rotate
        try:
            with open(file_path, "r", newline="") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if not header:
                    continue
                rows = list(reader)

            if filename == "nifty_50_feed.csv":
                # Keep last N rows globally
                rotated_rows = rows[-keep_count:]
            else:
                # Group by symbol and keep last N rows per symbol
                grouped = {}
                for row in rows:
                    if len(row) < 2:
                        continue
                    sym = row[1]
                    if sym not in grouped:
                        grouped[sym] = []
                    grouped[sym].append(row)
                
                rotated_rows = []
                for sym, sym_rows in grouped.items():
                    rotated_rows.extend(sym_rows[-keep_count:])
                
                # Sort by timestamp (column 0) to maintain chronological order
                try:
                    rotated_rows.sort(key=lambda x: x[0])
                except Exception:
                    pass

            # Write back
            with open(file_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(header)
                writer.writerows(rotated_rows)
            print(f"🧹 Rotated {filename}: Kept {len(rotated_rows)} rows (Archived copy saved)")
        except Exception as e:
            print(f"⚠️ Error rotating {filename}: {e}")

    # 2. Archive and truncate .log files
    for filename in log_files_to_truncate:
        file_path = os.path.join(LOGS_DIR, filename)
        if not os.path.exists(file_path):
            continue

        # Copy to archive
        shutil.copy(file_path, os.path.join(current_archive_dir, filename))
        
        # Truncate
        try:
            with open(file_path, "w") as f:
                f.write("")
            print(f"📄 Truncated log file: {filename} (Archived copy saved)")
        except Exception as e:
            print(f"⚠️ Error truncating {filename}: {e}")

    # 3. Clean radar_watchlist.json (reset to [])
    radar_wl_path = os.path.join(DATA_DIR, "radar_watchlist.json")
    if os.path.exists(radar_wl_path):
        try:
            shutil.copy(radar_wl_path, os.path.join(current_archive_dir, "radar_watchlist.json"))
            with open(radar_wl_path, "w") as f:
                json.dump([], f)
            print("🎯 Reset radar_watchlist.json to [] (Archived copy saved)")
        except Exception as e:
            print(f"⚠️ Error resetting radar watchlist: {e}")

if __name__ == "__main__":
    rotate_and_clean()
