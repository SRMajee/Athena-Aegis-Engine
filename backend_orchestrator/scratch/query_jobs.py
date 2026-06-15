import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.infra.db import async_session_maker, BacktestJob
import sqlalchemy as sa

async def main():
    async with async_session_maker() as session:
        result = await session.execute(
            sa.select(BacktestJob).order_by(BacktestJob.started_at.desc()).limit(10)
        )
        jobs = result.scalars().all()
        for j in jobs:
            print(f"ID: {j.id} | Status: {j.status} | Started: {j.started_at} | Finished: {j.completed_at} | Summary: {j.summary}")

if __name__ == "__main__":
    asyncio.run(main())
