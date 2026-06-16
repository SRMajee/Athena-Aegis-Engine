import sys
from pathlib import Path
import pandas as pd

def main():
    root = Path(__file__).resolve().parent.parent.parent
    spy_file = root / "data" / "SPY" / "2010" / "01" / "2010-01-04.parquet"
    if not spy_file.exists():
        print("SPY file not found.")
        return
    df = pd.read_parquet(spy_file)
    print(f"SPY Shape: {df.shape}")
    print(f"SPY Columns: {list(df.columns)}")
    print(f"SPY Head:\n{df.head(2)}")

if __name__ == "__main__":
    main()
