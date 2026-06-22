import sys
import os
import argparse
from pathlib import Path
from dotenv import load_dotenv

def main():
    parser = argparse.ArgumentParser(description="Download Alpaca options bar data and auto-register it for backtesting.")
    parser.add_argument("-s", "--symbol", required=True, help="Underlying symbol (e.g. AAPL, SPY)")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="End date (YYYY-MM-DD), defaults to start date")
    
    args = parser.parse_args()
    
    # 1. Resolve paths
    root_dir = Path(__file__).resolve().parent.parent
    data_dir = root_dir / "data"
    
    # 2. Load Alpaca credentials from root .env
    load_dotenv(dotenv_path=root_dir / ".env")
    api_key = os.getenv("ALPACA_API_KEY_ID")
    api_secret = os.getenv("ALPACA_API_SECRET_KEY")
    
    if not api_key or not api_secret:
        print("Error: Alpaca API credentials not found in root .env file.")
        sys.exit(1)
        
    symbol = args.symbol.upper()
    start_date = args.start
    end_date = args.end or start_date
    
    print(f"Initializing download for {symbol} ({start_date} to {end_date})...")
    
    # 3. Add root to path and import downloader function
    sys.path.insert(0, str(root_dir))
    try:
        from download_alpaca_options import download_data
    except ImportError as e:
        print(f"Error: Failed to import download utility: {e}")
        sys.exit(1)
        
    # 4. Perform download
    try:
        download_data(symbol, start_date, end_date, api_key, api_secret, data_dir)
        print(f"\n[OK] Options data for {symbol} has been successfully downloaded into {data_dir}/{symbol}.")
        print("It is now automatically indexed and available for backtesting.")
    except Exception as e:
        print(f"\n[ERROR] Download failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
