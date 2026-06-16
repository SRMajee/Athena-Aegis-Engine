import sys
from pathlib import Path
import pandas as pd

def main():
    root = Path(__file__).resolve().parent.parent.parent
    
    spy_file = root / "data" / "SPY" / "2010" / "01" / "2010-01-04.parquet"
    aapl_file = root / "data" / "AAPL" / "2025" / "06" / "2025-06-02.parquet"
    
    if spy_file.exists():
        df_spy = pd.read_parquet(spy_file)
        print("=== SPY (2010-01-04) ===")
        print(f"Total Rows: {len(df_spy)}")
        print(f"Unique Option Symbols: {df_spy['symbol'].nunique()}")
        print(f"Unique Timestamps: {df_spy['ts_recv'].nunique()}")
    else:
        print("SPY file not found.")
        
    if aapl_file.exists():
        df_aapl = pd.read_parquet(aapl_file)
        print("\n=== AAPL (2025-06-02) ===")
        print(f"Total Rows: {len(df_aapl)}")
        print(f"Unique Option Symbols: {df_aapl['symbol'].nunique()}")
        print(f"Unique Timestamps: {df_aapl['ts_recv'].nunique()}")
    else:
        print("AAPL file not found.")

if __name__ == "__main__":
    main()
