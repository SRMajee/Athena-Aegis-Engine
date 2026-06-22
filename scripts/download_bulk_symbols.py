import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

def main():
    parser = argparse.ArgumentParser(description="Bulk download options contracts for symbols in symbols.txt if not already downloaded.")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="End date (YYYY-MM-DD), defaults to start date")
    parser.add_argument("--limit-contracts", type=int, default=1000, help="Maximum option contracts to download per symbol")
    parser.add_argument("--symbols-file", default="symbols.txt", help="Path to symbols.txt file")
    
    args = parser.parse_args()
    
    root_dir = Path(__file__).resolve().parent.parent
    data_dir = root_dir / "data"
    symbols_path = root_dir / args.symbols_file
    
    if not symbols_path.exists():
        print(f"Error: Symbols file not found at {symbols_path}")
        sys.exit(1)
        
    # Load credentials
    load_dotenv(dotenv_path=root_dir / ".env")
    api_key = os.getenv("ALPACA_API_KEY_ID")
    api_secret = os.getenv("ALPACA_API_SECRET_KEY")
    
    if not api_key or not api_secret:
        print("Error: Alpaca API credentials not found in root .env file.")
        sys.exit(1)
        
    # Read symbols
    with open(symbols_path, "r") as f:
        symbols = [line.strip().upper() for line in f if line.strip()]
        
    print(f"Loaded {len(symbols)} symbols from {args.symbols_file}")
    
    # Add root to python path to import download utility
    sys.path.insert(0, str(root_dir))
    try:
        from download_alpaca_options import download_data
    except ImportError as e:
        print(f"Error: Failed to import download utility: {e}")
        sys.exit(1)
        
    # Process symbols one by one
    start_date = args.start
    end_date = args.end or start_date
    
    for idx, sym in enumerate(symbols):
        sym_dir = data_dir / sym
        # A symbol is considered downloaded if its directory exists and contains files/subdirectories
        if sym_dir.exists() and any(sym_dir.iterdir()):
            print(f"[{idx+1}/{len(symbols)}] Skipping {sym} - already downloaded.")
            continue
            
        print(f"\n==========================================")
        print(f"[{idx+1}/{len(symbols)}] Downloading options for {sym}...")
        print(f"==========================================")
        
        try:
            download_data(
                symbol=sym,
                start_date_str=start_date,
                end_date_str=end_date,
                api_key=api_key,
                api_secret=api_secret,
                output_dir=data_dir,
                max_contracts=args.limit_contracts
            )
            print(f"[OK] Completed download for {sym}.")
        except Exception as e:
            print(f"[ERROR] Failed downloading {sym}: {e}")
            # Continue to next symbol even if one fails
            continue

if __name__ == "__main__":
    main()
