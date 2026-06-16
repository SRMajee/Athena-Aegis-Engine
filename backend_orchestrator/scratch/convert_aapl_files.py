import os
import sys
import glob
from pathlib import Path
from datetime import datetime
import pandas as pd
import httpx
from dotenv import load_dotenv

# Load env from root
root = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=root / ".env")

def rfc_to_epoch_nanos(rfc_str: str) -> int:
    try:
        dt = datetime.strptime(rfc_str.replace("Z", "+00:00"), "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        dt = datetime.strptime(rfc_str.replace("Z", "+00:00"), "%Y-%m-%dT%H:%M:%S.%f%z")
    return int(dt.timestamp() * 1e9)

def fetch_underlying_prices(symbol: str, start_date_str: str, end_date_str: str, headers: dict) -> dict:
    url = f"https://data.alpaca.markets/v2/stocks/{symbol}/bars"
    prices = {}
    page_token = None
    
    start_rfc = f"{start_date_str}T00:00:00Z"
    end_rfc = f"{end_date_str}T23:59:59Z"
    
    print(f"Fetching underlying stock prices for {symbol} ({start_date_str} to {end_date_str})...")
    while True:
        params = {
            "timeframe": "5Min",
            "start": start_rfc,
            "end": end_rfc,
            "limit": 10000
        }
        if page_token:
            params["page_token"] = page_token
            
        resp = httpx.get(url, headers=headers, params=params, timeout=30.0)
        if resp.status_code != 200:
            print(f"Failed to fetch stock bars: {resp.text}")
            break
            
        data = resp.json()
        bars = data.get("bars", []) or []
        for bar in bars:
            ts = bar.get("t")
            prices[ts] = float(bar.get("c"))
            
        page_token = data.get("next_page_token")
        if not page_token:
            break
            
    print(f"Loaded {len(prices)} underlying price points.")
    return prices

def main():
    aapl_dir = root / "data" / "AAPL"
    parquet_files = sorted(list(aapl_dir.rglob("*.parquet")))
    
    if not parquet_files:
        print("No AAPL parquet files found.")
        return
        
    print(f"Found {len(parquet_files)} AAPL parquet files to convert.")
    
    # Extract date strings from filenames to get range
    dates = []
    for p in parquet_files:
        stem = p.stem # e.g. 2025-06-02
        if len(stem) == 10 and stem[4] == '-' and stem[7] == '-':
            dates.append(stem)
            
    if not dates:
        print("No valid daily files found.")
        return
        
    dates.sort()
    start_date = dates[0]
    end_date = dates[-1]
    
    api_key = os.getenv("ALPACA_API_KEY_ID")
    api_secret = os.getenv("ALPACA_API_SECRET_KEY")
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret
    }
    
    underlying_prices = fetch_underlying_prices("AAPL", start_date, end_date, headers)
    
    for p in parquet_files:
        print(f"Converting {p.relative_to(root)}...")
        df = pd.read_parquet(p)
        
        # Check if already converted
        if "ts_recv" in df.columns and "bid_px" in df.columns:
            print("  Already converted, skipping.")
            continue
            
        if "timestamp" not in df.columns:
            print("  Error: 'timestamp' column missing, skipping.")
            continue
            
        # Parse timestamp to nanos
        df["ts_recv"] = df["timestamp"].apply(rfc_to_epoch_nanos)
        
        # Map columns
        df["symbol"] = df["contract_symbol"]
        
        # Map prices
        df["bid_px"] = df["close"].astype(float)
        df["ask_px"] = df["close"].astype(float)
        df["bid_sz"] = 10.0
        df["ask_sz"] = 10.0
        
        # Map underlying prices
        def get_underlying_price(ts_str):
            return underlying_prices.get(ts_str, 0.0)
            
        df["underlying_bid_px"] = df["timestamp"].apply(get_underlying_price)
        df["underlying_ask_px"] = df["timestamp"].apply(get_underlying_price)
        df["underlying_bid_sz"] = 1000.0
        df["underlying_ask_sz"] = 1000.0
        
        # Select target columns
        target_cols = [
            "ts_recv", "symbol", "bid_px", "ask_px", "bid_sz", "ask_sz",
            "underlying_bid_px", "underlying_ask_px", "underlying_bid_sz", "underlying_ask_sz"
        ]
        df_converted = df[target_cols]
        df_converted.to_parquet(p, index=False)
        print(f"  Successfully converted {len(df_converted)} rows.")

if __name__ == "__main__":
    main()
