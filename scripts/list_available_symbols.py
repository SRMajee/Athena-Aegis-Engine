import urllib.request
import json
import sys

def main():
    url = "http://localhost:8085/api/files"
    print(f"Querying available symbols from: {url}")
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            
        print("\nAvailable Symbols for Backtesting:")
        print(f"{'Symbol':<10} | {'Type':<10} | {'Start Date':<12} | {'End Date':<12} | {'Days':<6} | {'Files':<6}")
        print("-" * 65)
        
        found = False
        for item in data:
            # Type 'segment' represents options datasets under data/
            if item.get("type") == "segment":
                symbol = item.get("name", "N/A")
                date_start = item.get("date_start") or "N/A"
                date_end = item.get("date_end") or "N/A"
                days = item.get("number_of_days") or 0
                files = item.get("file_count") or 0
                print(f"{symbol:<10} | {'Options':<10} | {date_start:<12} | {date_end:<12} | {days:<6} | {files:<6}")
                found = True
            elif item.get("type") == "parquet" and not item.get("name", "").startswith("backtest_"):
                # Individual parquet files
                symbol = item.get("name", "N/A").replace(".parquet", "")
                print(f"{symbol:<10} | {'Equity':<10} | {'N/A':<12} | {'N/A':<12} | {'N/A':<6} | {1:<6}")
                found = True
                
        if not found:
            print("No symbols or segments found.")
            
    except Exception as e:
        print(f"Error querying API: {e}")
        print("Please ensure the FastAPI backend is running on port 8085.")
        sys.exit(1)

if __name__ == "__main__":
    main()
