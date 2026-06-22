import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv
import httpx

def main():
    parser = argparse.ArgumentParser(description="List all active, options-eligible underlying symbols available on Alpaca.")
    parser.add_argument("-f", "--filter", help="Search pattern or prefix to filter symbols (e.g., TS, AA)")
    parser.add_argument("-o", "--output", help="Save the complete list to a text file (e.g. symbols.txt)")
    
    args = parser.parse_args()
    
    # Load credentials from root .env
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
    
    url = "https://paper-api.alpaca.markets/v2/assets"
    print("Fetching active assets from Alpaca API...")
    
    try:
        resp = httpx.get(url, headers=headers, params={"status": "active", "asset_class": "us_equity"}, timeout=30.0)
        if resp.status_code != 200:
            print(f"Error calling assets API: {resp.text}")
            sys.exit(1)
        
        assets = resp.json()
    except Exception as e:
        print(f"Connection error: {e}")
        sys.exit(1)
        
    # Filter for active and options-eligible equities
    eligible_symbols = []
    for asset in assets:
        is_eligible = asset.get("options_eligible", False) or "has_options" in asset.get("attributes", [])
        if asset.get("status") == "active" and is_eligible:
            eligible_symbols.append({
                "symbol": asset.get("symbol"),
                "name": asset.get("name"),
                "exchange": asset.get("exchange")
            })
            
    # Sort symbols alphabetically
    eligible_symbols.sort(key=lambda x: x["symbol"])
    
    total_count = len(eligible_symbols)
    print(f"\nAlpaca Options-Eligible Symbols:")
    print(f"Total options-eligible symbols found: {total_count}")
    
    # Filter if search argument is provided
    if args.filter:
        search_term = args.filter.upper()
        eligible_symbols = [x for x in eligible_symbols if x["symbol"].startswith(search_term)]
        print(f"Symbols starting with '{search_term}': {len(eligible_symbols)}")
        
    # Save to file if output argument is provided
    if args.output:
        out_path = Path(args.output)
        with open(out_path, "w") as f:
            for s in eligible_symbols:
                f.write(f"{s['symbol']}\n")
        print(f"Saved {len(eligible_symbols)} symbols to {out_path.resolve()}")
        
    # Display the first 100 symbols
    print(f"\nShowing first 100 symbols:")
    print(f"{'Symbol':<10} | {'Exchange':<10} | {'Name':<50}")
    print("-" * 75)
    for s in eligible_symbols[:100]:
        print(f"{s['symbol']:<10} | {s['exchange']:<10} | {s['name'][:50]:<50}")
        
    if len(eligible_symbols) > 100:
        print(f"... and {len(eligible_symbols) - 100} more symbols.")

if __name__ == "__main__":
    main()
