import asyncio
import json
import httpx

async def main():
    print("=== TESTING REAL-TIME DATABASE UPDATES ===")
    
    url = "http://localhost:8085/api/run_backtest"
    payload = {
        "parquet": "SPY",
        "strategy": "IronCondorTestStrategy",
        "fee_rate": 0.35,
        "slippage_bps": 5.0,
        "risk_free_rate": 0.05,
        "iv_price_mode": "mid",
        "strategy_setting": {},
        "start_date": "2010-01-04",
        "end_date": "2010-12-31" # Run a longer backtest so we can see real-time database polling!
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, timeout=10.0)
            data = resp.json()
            job_id = data.get("job_id")
            print(f"Backtest triggered. Job ID: {job_id}")
        except Exception as e:
            print(f"Request failed: {e}")
            return
            
    # Poll database for trades in real-time
    db_url = f"http://localhost:8085/api/orders-trades/db?strategy=IronCondorTestStrategy&record_type=Trade"
    
    print("Polling database for trades every 0.5 seconds...")
    for _ in range(30):
        await asyncio.sleep(0.5)
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(db_url, timeout=5.0)
                db_data = resp.json()
                records = db_data.get("records", [])
                print(f"DB Poll: found {len(records)} trades in database.")
                if len(records) > 0:
                    print(f"  First trade: {records[0]}")
            except Exception as e:
                print(f"DB Poll failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
