import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv
import httpx

def fetch_contracts(symbol: str, status: str, headers: dict) -> list:
    url = "https://paper-api.alpaca.markets/v2/options/contracts"
    contracts = []
    page_token = None
    
    while True:
        params = {
            "underlying_symbols": symbol,
            "status": status,
            "limit": 10000
        }
        if page_token:
            params["page_token"] = page_token
            
        try:
            resp = httpx.get(url, headers=headers, params=params, timeout=15.0)
            if resp.status_code != 200:
                print(f"Error fetching {status} contracts: {resp.text}")
                break
            data = resp.json()
            contracts.extend(data.get("option_contracts", []))
            page_token = data.get("next_page_token")
            if not page_token:
                break
        except Exception as e:
            print(f"Connection error: {e}")
            break
            
    return contracts

def main():
    parser = argparse.ArgumentParser(description="List options contracts and available date ranges downloadable from Alpaca.")
    parser.add_argument("-s", "--symbol", required=True, help="Underlying symbol (e.g. AAPL, SPY, MSFT)")
    
    args = parser.parse_args()
    symbol = args.symbol.upper()
    
    # Resolve paths and load credentials from .env
    root_dir = Path(__file__).resolve().parent.parent
    load_dotenv(dotenv_path=root_dir / ".env")
    
    api_key = os.getenv("ALPACA_API_KEY_ID")
    api_secret = os.getenv("ALPACA_API_SECRET_KEY")
    
    if not api_key or not api_secret:
        print("Error: Alpaca API credentials not found in root .env file.")
        sys.exit(1)
        
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret
    }
    
    print(f"Querying downloadable options contracts for {symbol} from Alpaca API...")
    
    active = fetch_contracts(symbol, "active", headers)
    inactive = fetch_contracts(symbol, "inactive", headers)
    all_contracts = active + inactive
    
    if not all_contracts:
        print(f"No options contracts found for underlying '{symbol}'.")
        return
        
    # Group by expiration date
    expirations = {}
    for c in all_contracts:
        exp = c.get("expiration_date")
        if exp:
            expirations[exp] = expirations.get(exp, 0) + 1
            
    sorted_expirations = sorted(expirations.keys())
    
    print(f"\nContracts Summary for {symbol}:")
    print(f"Total Available Option Symbols: {len(all_contracts)}")
    if sorted_expirations:
        print(f"Earliest Expiration (Start Date): {sorted_expirations[0]}")
        print(f"Furthest Expiration (End Date):   {sorted_expirations[-1]}")
        
    print(f"\nAvailable Expiration Dates and Contract Counts:")
    print(f"{'Expiration Date':<17} | {'Contract Count':<15}")
    print("-" * 35)
    for exp in sorted_expirations[:30]: # Show first 30 expiration dates
        print(f"{exp:<17} | {expirations[exp]:<15}")
        
    if len(sorted_expirations) > 30:
        print(f"... and {len(sorted_expirations) - 30} more expiration dates.")

if __name__ == "__main__":
    main()
