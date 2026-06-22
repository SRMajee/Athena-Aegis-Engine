import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

def main():
    parser = argparse.ArgumentParser(description="Download option contracts for up to 20 symbols per letter prefix from A-Z.")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="End date (YYYY-MM-DD), defaults to start date")
    parser.add_argument("--limit-contracts", type=int, default=1000, help="Maximum option contracts to download per symbol")
    parser.add_argument("--symbols-file", default="symbols.txt", help="Path to symbols.txt file")
    parser.add_argument("--target-per-prefix", type=int, default=20, help="Target number of downloaded symbols per letter prefix")
    
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
        
    # Read and group symbols by starting letter
    prefix_map = {}
    with open(symbols_path, "r") as f:
        for line in f:
            sym = line.strip().upper()
            if not sym:
                continue
            first_letter = sym[0]
            if first_letter.isalpha():
                if first_letter not in prefix_map:
                    prefix_map[first_letter] = []
                prefix_map[first_letter].append(sym)
                
    # Check already downloaded symbols under data/
    downloaded_symbols = set()
    if data_dir.exists():
        for item in data_dir.iterdir():
            if item.is_dir() and any(item.iterdir()):
                # Exclude 'temp' or other infrastructure folders if any
                if item.name.upper() != "TEMP":
                    downloaded_symbols.add(item.name.upper())
                    
    print(f"Total already downloaded symbols found: {len(downloaded_symbols)}")
    
    # Add root to python path to import download utility
    sys.path.insert(0, str(root_dir))
    try:
        from download_alpaca_options import download_data
    except ImportError as e:
        print(f"Error: Failed to import download utility: {e}")
        sys.exit(1)
        
    start_date = args.start
    end_date = args.end or start_date
    target = args.target_per_prefix
    
    # Process each prefix A-Z
    for letter in sorted(prefix_map.keys()):
        all_syms_with_prefix = prefix_map[letter]
        
        # Count already downloaded for this prefix
        downloaded_with_prefix = [s for s in all_syms_with_prefix if s in downloaded_symbols]
        count_downloaded = len(downloaded_with_prefix)
        
        print(f"\n==========================================")
        print(f"Prefix '{letter}': {count_downloaded}/{target} symbols already downloaded.")
        print(f"==========================================")
        
        if count_downloaded >= target:
            print(f"Target of {target} symbols for prefix '{letter}' is already met. Skipping.")
            continue
            
        needed = target - count_downloaded
        to_download = [s for s in all_syms_with_prefix if s not in downloaded_symbols]
        
        print(f"Need to download {needed} more symbols starting with '{letter}'.")
        
        download_count = 0
        for sym in to_download:
            if download_count >= needed:
                break
                
            print(f"\n---> [{letter}] Downloading {sym} ({download_count + 1}/{needed})...")
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
                print(f"[OK] Successfully downloaded {sym}.")
                download_count += 1
            except Exception as e:
                print(f"[ERROR] Failed downloading {sym}: {e}")
                # Continue trying other symbols of the prefix if one fails
                continue
                
        print(f"Finished prefix '{letter}'. Downloaded {download_count} new symbols.")

if __name__ == "__main__":
    main()
