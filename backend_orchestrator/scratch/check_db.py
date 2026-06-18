import asyncio
import dotenv
dotenv.load_dotenv()
import sqlalchemy as sa
from src.infra.db import async_session_maker, RiskSnapshot

async def main():
    async with async_session_maker() as session:
        result = await session.execute(sa.text("SELECT model_id, COUNT(*) FROM risk_snapshot GROUP BY model_id"))
        rows = result.fetchall()
        print("=== Database Risk Snapshots (First 10) ===")
        for r in rows:
            print(r)

if __name__ == "__main__":
    asyncio.run(main())
