import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.infra.task_queue import resolve_parquet_path
import pandas as pd

def main():
    print("Testing resolve_parquet_path for AAPL...")
    try:
        resolved_path, is_temp = resolve_parquet_path("AAPL", "2025-06-02", "2025-06-06", "test_job_123")
        print(f"Resolved path: {resolved_path}")
        print(f"Is temp: {is_temp}")
        
        df = pd.read_parquet(resolved_path)
        print(f"DataFrame loaded successfully. Shape: {df.shape}")
        print(f"Columns: {list(df.columns)}")
        print(f"Head:\n{df.head(2)}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
