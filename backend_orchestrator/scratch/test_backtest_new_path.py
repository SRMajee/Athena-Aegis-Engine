import httpx
import asyncio
import json

async def main():
    payload = {
        "parquet": "SPY",
        "strategy": "StraddleTestStrategy",
        "fee_rate": 0.35,
        "slippage_bps": 5.0,
        "risk_free_rate": 0.05,
        "iv_price_mode": "mid",
        "strategy_setting": {},
        "start_date": "2010-01-04",
        "end_date": "2010-01-08"
    }
    
    async with httpx.AsyncClient() as client:
        print("Submitting backtest...")
        resp = await client.post("http://localhost:8086/api/run_backtest", json=payload, timeout=10.0)
        print("Status Code:", resp.status_code)
        print("Response:", resp.json())
        
        job_id = resp.json().get("job_id")
        
        print(f"Waiting for job {job_id} to finish...")
        for _ in range(30):
            status_resp = await client.get(f"http://localhost:8086/api/backtests")
            data = status_resp.json()
            # print("Raw API response:", data)
            
            # Extract jobs list from data (usually it's {"backtests": [...]} or data directly if list)
            jobs = data.get("backtests", []) if isinstance(data, dict) else data
            
            job = next((j for j in jobs if j.get("id") == job_id), None)
            if job:
                print(f"Job Status: {job.get('status')}")
                if job.get("status") in ("COMPLETED", "FAILED"):
                    print("Job result summary:")
                    print(json.dumps(job, indent=2))
                    break
            else:
                print("Job not found in listing yet...")
            await asyncio.sleep(1.0)

if __name__ == "__main__":
    asyncio.run(main())
