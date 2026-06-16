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

async def test_contracts():
    url = "https://paper-api.alpaca.markets/v2/options/contracts"
    params = {
        "underlying_symbols": "AAPL",
        "status": "inactive",  # Fetch expired/inactive contracts
        "limit": 10
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, params=params)
        print("Status:", resp.status_code)
        if resp.status_code == 200:
            data = resp.json()
            contracts = data.get("option_contracts", [])
            print(f"Found {len(contracts)} option contracts.")
            if contracts:
                print("Sample inactive contract status:", contracts[0].get("status"))
                print("Sample inactive contract expiry:", contracts[0].get("expiration_date"))
        else:
            print("Error response:", resp.text)

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_contracts())
