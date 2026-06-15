import asyncio
import httpx
import sys
from pathlib import Path

# Add backend_orchestrator directory to python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.infra.db import async_session_maker, BacktestJob
import sqlalchemy as sa
from uuid import UUID

strategies = [
    "StraddleTestStrategy",
    "IronCondorTestStrategy",
    "IvMeanRevertStrategy",
    "StraddleInventoryScalperStrategy"
]

async def check_job_status(correlation_id: str):
    async with async_session_maker() as session:
        result = await session.execute(
            sa.select(BacktestJob).where(BacktestJob.correlation_id == correlation_id)
        )
        job = result.scalar_one_or_none()
        if job:
            return job.status, job.summary
    return "UNKNOWN", None

async def run_verification():
    print("==================================================")
    print("   Starting verification of all 4 strategies")
    print("==================================================")

    async with httpx.AsyncClient() as client:
        for strat in strategies:
            print(f"\n---> Launching backtest for strategy: {strat}")
            
            payload = {
                "parquet": "SPY",
                "strategy": strat,
                "fee_rate": 0.35,
                "slippage_bps": 5.0,
                "risk_free_rate": 0.05,
                "iv_price_mode": "mid",
                "strategy_setting": {},
                "start_date": "2010-01-04",
                "end_date": "2010-01-22"
            }
            
            try:
                res = await client.post("http://localhost:8086/api/run_backtest", json=payload, timeout=10.0)
                if res.status_code != 202:
                    print(f"Error starting backtest: {res.status_code} - {res.text}")
                    continue
                
                resp_json = res.json()
                if resp_json.get("status") != "ok":
                    print(f"Failed to start backtest: {resp_json}")
                    continue
                
                job_id = resp_json["job_id"]
                print(f"Enqueued successfully. Job ID: {job_id}")
                
                # Poll job status
                while True:
                    await asyncio.sleep(1.0)
                    status, summary = await check_job_status(job_id)
                    print(f"Status: {status}...")
                    if status in ["COMPLETE", "FAILED", "SUCCESS", "ERROR"]:
                        print(f"Finished with status: {status}")
                        if summary:
                            print(f"Summary: {summary}")
                        else:
                            # Let's query PostgreSQL for trades and orders count
                            async with async_session_maker() as session:
                                tc = await session.execute(sa.text("SELECT count(*) FROM trades WHERE strategy_name = :strat"), {"strat": strat})
                                oc = await session.execute(sa.text("SELECT count(*) FROM orders WHERE strategy_name = :strat"), {"strat": strat})
                                trade_count = tc.scalar()
                                order_count = oc.scalar()
                                print(f"DB Trades count: {trade_count}, DB Orders count: {order_count}")
                        break
            except Exception as e:
                print(f"Failed to run strategy {strat}: {e}")

if __name__ == "__main__":
    asyncio.run(run_verification())
