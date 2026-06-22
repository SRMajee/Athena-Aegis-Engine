import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np

def convert_year(year: int, spy_dir: Path):
    yearly_file = spy_dir / f"spy_eod_{year}.parquet"
    if not yearly_file.exists():
        print(f"Yearly file for {year} not found: {yearly_file}")
        return
        
    print(f"\nProcessing {yearly_file.name}...")
    
    # 1. Read yearly parquet
    try:
        df = pd.read_parquet(yearly_file)
    except Exception as e:
        print(f"Error reading yearly parquet: {e}")
        return
        
    # 2. Extract and format strikes
    strikes_int = (df['[STRIKE]'] * 1000).astype(int)
    strikes_str = strikes_int.apply(lambda x: f"{x:08d}")
    
    # 3. Extract and format expiration dates
    exp_clean = df['[EXPIRE_DATE]'].str.replace("-", "", regex=False)
    exp_yymmdd = exp_clean.str[2:8]
    
    # 4. Generate OCC symbols
    df['call_symbol'] = "SPY   " + exp_yymmdd + "C" + strikes_str
    df['put_symbol'] = "SPY   " + exp_yymmdd + "P" + strikes_str
    
    # 5. Generate ts_recv in nanoseconds
    df['ts_recv'] = (df['[QUOTE_UNIXTIME]'] * 1e9).astype(np.int64)
    
    # 6. Group by quote date
    grouped = df.groupby('[QUOTE_DATE]')
    total_dates = len(grouped)
    print(f"Total dates to process: {total_dates}")
    
    for date_str, group in grouped:
        # Create output directory: data/SPY/YYYY/MM/
        dt_parts = date_str.split("-")
        year_str = dt_parts[0]
        month_str = dt_parts[1]
        
        target_dir = spy_dir / year_str / month_str
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / f"{date_str}.parquet"
        
        # Build call rows
        calls = pd.DataFrame({
            "ts_recv": group['ts_recv'],
            "symbol": group['call_symbol'],
            "bid_px": group['[C_BID]'].astype(float),
            "ask_px": group['[C_ASK]'].astype(float),
            "bid_sz": 100.0, # Standard default size
            "ask_sz": 100.0,
            "underlying_bid_px": group['[UNDERLYING_LAST]'].astype(float),
            "underlying_ask_px": group['[UNDERLYING_LAST]'].astype(float),
            "underlying_bid_sz": 1000.0,
            "underlying_ask_sz": 1000.0
        })
        # Remove empty bid/ask quotes
        calls = calls[calls['bid_px'].notna() & calls['ask_px'].notna()]
        
        # Build put rows
        puts = pd.DataFrame({
            "ts_recv": group['ts_recv'],
            "symbol": group['put_symbol'],
            "bid_px": group['[P_BID]'].astype(float),
            "ask_px": group['[P_ASK]'].astype(float),
            "bid_sz": 100.0,
            "ask_sz": 100.0,
            "underlying_bid_px": group['[UNDERLYING_LAST]'].astype(float),
            "underlying_ask_px": group['[UNDERLYING_LAST]'].astype(float),
            "underlying_bid_sz": 1000.0,
            "underlying_ask_sz": 1000.0
        })
        puts = puts[puts['bid_px'].notna() & puts['ask_px'].notna()]
        
        # Combine calls and puts
        daily_df = pd.concat([calls, puts], ignore_index=True)
        daily_df.drop_duplicates(subset=["symbol", "ts_recv"], keep="last", inplace=True)
        daily_df.sort_values(by=["symbol", "ts_recv"], inplace=True)
        
        # Save to parquet
        daily_df.to_parquet(target_file, index=False)
        
    print(f"Completed {year}. Deleting original yearly file...")
    try:
        os.remove(yearly_file)
    except Exception as e:
        print(f"Failed to remove yearly file: {e}")

def main():
    root_dir = Path(__file__).resolve().parent.parent
    spy_dir = root_dir / "data" / "SPY"
    
    if not spy_dir.exists():
        print(f"SPY directory not found at: {spy_dir}")
        sys.exit(1)
        
    # Process all yearly files from 2011 to 2023
    for year in range(2011, 2024):
        convert_year(year, spy_dir)
        
    print("\n[OK] All yearly SPY files successfully converted to daily options layout.")

if __name__ == "__main__":
    main()
