import asyncio
import dotenv
dotenv.load_dotenv()
import sqlalchemy as sa
from src.infra.db import async_session_maker, RiskSnapshot, BacktestJob

async def main():
    async with async_session_maker() as session:
        # Find the latest job
        res = await session.execute(sa.select(BacktestJob).order_by(BacktestJob.started_at.desc()).limit(1))
        job = res.scalar_one_or_none()
        if not job:
            print("No jobs found!")
            return
            
        print(f"Latest Job ID: {job.id}, Status: {job.status}, Started: {job.started_at}")
        
        # Query risk snapshots count grouped by model_id for this job
        res_snap = await session.execute(
            sa.text("SELECT model_id, COUNT(*), MIN(tick_idx), MAX(tick_idx) FROM risk_snapshot WHERE job_id = :job_id GROUP BY model_id"),
            {"job_id": job.id}
        )
        rows = res_snap.fetchall()
        print("\n=== Risk Snapshots for this Job ===")
        for r in rows:
            print(r)
            
        # Query some sample snapshots
        res_sample = await session.execute(
            sa.select(RiskSnapshot).where(RiskSnapshot.job_id == job.id).order_by(RiskSnapshot.tick_idx, RiskSnapshot.model_id).limit(25)
        )
        samples = res_sample.scalars().all()
        print("\n=== Sample Snapshots ===")
        for s in samples:
            print(f"Tick: {s.tick_idx} | Model: {s.model_id} | Delta: {s.delta:.4f} | Gamma: {s.gamma:.4f} | PnL: {s.pnl:.4f}")

if __name__ == "__main__":
    asyncio.run(main())
