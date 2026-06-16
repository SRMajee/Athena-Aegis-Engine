import os
from pathlib import Path
import httpx
from dotenv import load_dotenv

root = Path(__file__).resolve().parent.parent.parent
load_dotenv(root / ".env")

API_KEY = os.getenv("ALPACA_API_KEY_ID")
API_SECRET = os.getenv("ALPACA_API_SECRET_KEY")

headers = {
    "APCA-API-KEY-ID": API_KEY,
    "APCA-API-SECRET-KEY": API_SECRET
}

async def test_bars():
    url = "https://data.alpaca.markets/v1beta1/options/bars"
    params = {
        "symbols": "AAPL260615C00250000",
        "timeframe": "5Min",
        "start": "2026-06-11T00:00:00Z", # A recent date where it was active
        "end": "2026-06-12T23:59:59Z",
        "limit": 10
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, params=params)
        print("Status:", resp.status_code)
        if resp.status_code == 200:
            data = resp.json()
            print("Response Keys:", list(data.keys()))
            bars = data.get("bars", {})
            for contract, bar_list in bars.items():
                print(f"Contract {contract} has {len(bar_list)} bars.")
                if bar_list:
                    print("Sample bar:", bar_list[0])
        else:
            print("Error response:", resp.text)

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_bars())
