import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Define root and load download utility
root_dir = Path("C:/Users/User/Desktop/Affinity-Core")
sys.path.insert(0, str(root_dir))
from download_alpaca_options import download_data

load_dotenv(dotenv_path=root_dir / ".env")
api_key = os.getenv("ALPACA_API_KEY_ID")
api_secret = os.getenv("ALPACA_API_SECRET_KEY")

if not api_key or not api_secret:
    print("Error: Alpaca API credentials not found.")
    sys.exit(1)

data_dir = root_dir / "data"
symbols = [d.name for d in data_dir.iterdir() if d.is_dir() and d.name != "temp"]

print(f"Found {len(symbols)} symbol directories in data/ to extend.")

# Extend all symbols to cover the full 2024-06-01 to 2026-01-02 range (AAPL scale)
start_date = "2024-06-01"
end_date = "2026-01-02"

downloaded_count = 0
for idx, sym in enumerate(sorted(symbols)):
    # Skip major symbols that are already fully populated (like AAPL/SPY which already have 399+ days)
    sym_dir = data_dir / sym
    parquet_files = list(sym_dir.glob("**/*.parquet"))
    if len(parquet_files) > 100:
        print(f"[{idx+1}/{len(symbols)}] Skipping {sym} - already has {len(parquet_files)} days of data.")
        continue
        
    print(f"\n==========================================")
    print(f"[{idx+1}/{len(symbols)}] Extending options data for {sym} ({start_date} ~ {end_date})...")
    print(f"==========================================")
    
    try:
        download_data(
            symbol=sym,
            start_date_str=start_date,
            end_date_str=end_date,
            api_key=api_key,
            api_secret=api_secret,
            output_dir=data_dir,
            max_contracts=1000
        )
        print(f"[OK] Completed extension for {sym}.")
        downloaded_count += 1
    except Exception as e:
        print(f"[ERROR] Failed extending {sym}: {e}")
        continue
    
    # Sleep to respect Alpaca API rate limits
    time.sleep(2.0)

print(f"\nBulk range extension completed. Successfully extended options for {downloaded_count} symbols.")
