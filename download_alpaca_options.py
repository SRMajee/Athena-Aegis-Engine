#!/usr/bin/env python
"""
Alpaca Options Data Downloader
Downloads 5-minute options bars from Alpaca Options Data API
and saves them to the deep nested Parquet layout:
data/{UNDERLYING}/{YYYY}/{MM}/{YYYY-MM-DD}.parquet
"""
import os
import sys
import time
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import httpx
import pandas as pd
from dotenv import load_dotenv

# Load credentials from .env file
load_dotenv()

ALPACA_DATA_BASE_URL = "https://data.alpaca.markets/v1beta1/options"

def parse_occ_symbol(symbol: str) -> dict:
    """
    Parses OCC symbol format: [TICKER][YYMMDD][C/P][STRIKE_PRICE]
    e.g. SPY260618C00450000 -> SPY, 2026-06-18, C, 450.00
    """
    ticker = symbol[:-15]
    date_str = symbol[-15:-9]
    option_type = symbol[-9]
    strike_str = symbol[-8:]
    
    expiry = f"20{date_str[0:2]}-{date_str[2:4]}-{date_str[4:6]}"
    strike = f"{float(strike_str) / 1000.0:.3f}"
    return {
        "underlying": ticker,
        "expiry": expiry,
        "type": option_type,
        "strike": strike
    }

def fetch_all_contracts(underlying: str, status: str, headers: dict) -> list:
    url = "https://paper-api.alpaca.markets/v2/options/contracts"
    contracts = []
    page_token = None
    
    while True:
        params = {
            "underlying_symbols": underlying,
            "status": status,
            "limit": 10000
        }
        if page_token:
            params["page_token"] = page_token
            
        resp = httpx.get(url, headers=headers, params=params, timeout=30.0)
        if resp.status_code != 200:
            print(f"Failed to fetch contracts ({status}): {resp.text}")
            break
            
        data = resp.json()
        contracts.extend(data.get("option_contracts", []))
        
        page_token = data.get("next_page_token")
        if not page_token:
            break
            
    return contracts

import re

def get_contracts_for_range(symbol: str, start_date_str: str, headers: dict) -> list:
    print(f"Resolving active and inactive options contracts for {symbol}...")
    active = fetch_all_contracts(symbol, "active", headers)
    inactive = fetch_all_contracts(symbol, "inactive", headers)
    
    all_contracts = active + inactive
    
    # OCC symbol regex matching Alpaca's expected format: e.g. AAPL260615C00250000
    occ_pattern = re.compile(r"^[A-Z]{1,5}\d{6,7}[CP]\d{8}$")
    
    # Filter contracts where expiration_date >= start_date_str and match OCC format
    valid_symbols = []
    for c in all_contracts:
        exp = c.get("expiration_date", "")
        if exp >= start_date_str:
            contract_symbol = c["symbol"]
            if occ_pattern.match(contract_symbol):
                valid_symbols.append(contract_symbol)
            
    print(f"Found {len(all_contracts)} total contracts. {len(valid_symbols)} match OCC format and date range >= {start_date_str}.")
    return valid_symbols

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

def download_data(symbol: str, start_date_str: str, end_date_str: str, api_key: str, api_secret: str, output_dir: Path):
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret
    }
    
    valid_contract_symbols = get_contracts_for_range(symbol, start_date_str, headers)
    if not valid_contract_symbols:
        print("No valid contracts found for the date range.")
        return
        
    underlying_prices = fetch_underlying_prices(symbol, start_date_str, end_date_str, headers)
        
    start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date_str, "%Y-%m-%d")
    
    # Split contract symbols into batches of 200
    chunk_size = 200
    batches = [valid_contract_symbols[i:i + chunk_size] for i in range(0, len(valid_contract_symbols), chunk_size)]
    
    print(f"Split {len(valid_contract_symbols)} contracts into {len(batches)} batches.")
    
    start_rfc = f"{start_date_str}T00:00:00Z"
    end_rfc = f"{end_date_str}T23:59:59Z"
    
    for i, batch in enumerate(batches):
        print(f"Fetching batch {i+1}/{len(batches)} ({len(batch)} contracts)...")
        symbols_query = ",".join(batch)
        page_token = None
        bars_by_date = {}
        
        while True:
            params = {
                "symbols": symbols_query,
                "timeframe": "5Min",
                "start": start_rfc,
                "end": end_rfc,
                "limit": 10000
            }
            if page_token:
                params["page_token"] = page_token
                
            response = httpx.get(f"{ALPACA_DATA_BASE_URL}/bars", headers=headers, params=params, timeout=45.0)
            
            if response.status_code == 429:
                retry_after = int(response.headers.get("retry-after", 60))
                print(f"Rate limited. Waiting {retry_after} seconds...")
                time.sleep(retry_after)
                continue
                
            if response.status_code != 200:
                print(f"API Error ({response.status_code}): {response.text}")
                break
                
            data = response.json()
            bars_map = data.get("bars", {}) or {}
            
            total_bars_in_page = sum(len(bars) for bars in bars_map.values())
            print(f"  -> Received page with {len(bars_map)} contracts, {total_bars_in_page} total bars.")
            
            for contract, bars in bars_map.items():
                for bar in bars:
                    if bar.get("v", 0) == 0:
                        continue # Skip zero volume
                        
                    # Extract date YYYY-MM-DD from timestamp
                    ts_str = bar.get("t")
                    dt_str = ts_str.split("T")[0]
                    
                    if dt_str not in bars_by_date:
                        bars_by_date[dt_str] = []
                        
                    ts_recv = rfc_to_epoch_nanos(ts_str)
                    under_px = underlying_prices.get(ts_str, 0.0)
                    close_val = float(bar.get("c"))
                    
                    bars_by_date[dt_str].append({
                        "ts_recv": ts_recv,
                        "symbol": contract,
                        "bid_px": close_val,
                        "ask_px": close_val,
                        "bid_sz": 10.0,
                        "ask_sz": 10.0,
                        "underlying_bid_px": under_px,
                        "underlying_ask_px": under_px,
                        "underlying_bid_sz": 1000.0,
                        "underlying_ask_sz": 1000.0
                    })
            
            page_token = data.get("next_page_token")
            if not page_token:
                break
                
        # Incremental write at the end of each batch
        if bars_by_date:
            print(f"  -> Merging and saving batch {i+1}/{len(batches)} data across {len(bars_by_date)} days...")
            for date_str, daily_bars in bars_by_date.items():
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                year_str = dt.strftime("%Y")
                month_str = dt.strftime("%m")
                
                target_file = output_dir / symbol / year_str / month_str / f"{date_str}.parquet"
                
                df_new = pd.DataFrame(daily_bars)
                if target_file.exists():
                    try:
                        df_existing = pd.read_parquet(target_file)
                        df_combined = pd.concat([df_existing, df_new], ignore_index=True)
                    except Exception as e:
                        print(f"Error reading {target_file}, overwriting: {e}")
                        df_combined = df_new
                else:
                    df_combined = df_new
                
                df_combined.drop_duplicates(subset=["symbol", "ts_recv"], keep="last", inplace=True)
                df_combined.sort_values(by=["symbol", "ts_recv"], inplace=True)
                target_file.parent.mkdir(parents=True, exist_ok=True)
                df_combined.to_parquet(target_file, index=False)
                
        time.sleep(0.5) # Avoid hitting rate limits between batches

def main():
    parser = argparse.ArgumentParser(description="Download Alpaca options bar data.")
    parser.add_argument("-s", "--symbol", required=True, help="Underlying ticker (e.g. SPY, AAPL)")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="End date (YYYY-MM-DD), defaults to start date")
    parser.add_argument("--api-key", help="Alpaca API Key ID (defaults to ALPACA_API_KEY_ID env var)")
    parser.add_argument("--api-secret", help="Alpaca API Secret Key (defaults to ALPACA_API_SECRET_KEY env var)")
    
    args = parser.parse_args()
    
    api_key = args.api_key or os.getenv("ALPACA_API_KEY_ID")
    api_secret = args.api_secret or os.getenv("ALPACA_API_SECRET_KEY")
    
    if not api_key or not api_secret:
        print("Error: Alpaca API credentials must be provided via arguments or environment variables.")
        sys.exit(1)
        
    end_date = args.end or args.start
    workspace_root = Path(__file__).resolve().parent
    data_dir = workspace_root / "data"
    
    download_data(args.symbol.upper(), args.start, end_date, api_key, api_secret, data_dir)

if __name__ == "__main__":
    main()
