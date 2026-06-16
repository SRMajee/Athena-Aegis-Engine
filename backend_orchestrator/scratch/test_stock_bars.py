import os
import httpx
from dotenv import load_dotenv

from pathlib import Path
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env")

def main():
    api_key = os.getenv("ALPACA_API_KEY_ID")
    api_secret = os.getenv("ALPACA_API_SECRET_KEY")
    
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret
    }
    
    url = "https://data.alpaca.markets/v2/stocks/AAPL/bars"
    params = {
        "timeframe": "5Min",
        "start": "2025-06-02T13:30:00Z",
        "end": "2025-06-02T20:00:00Z",
        "limit": 100
    }
    
    resp = httpx.get(url, headers=headers, params=params)
    print(f"Status Code: {resp.status_code}")
    print(f"Response: {resp.text[:500]}")

if __name__ == "__main__":
    main()
