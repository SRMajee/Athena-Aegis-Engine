import asyncio
import sys
from pathlib import Path
from datetime import datetime

sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.infra.db import async_session_maker
import sqlalchemy as sa

async def main():
    async with async_session_maker() as session:
        result = await session.execute(
            sa.text("SELECT timestamp, price, volume, symbol FROM trades LIMIT 10")
        )
        rows = result.fetchall()
        for idx, row in enumerate(rows):
            ts_str, price, volume, symbol = row
            print(f"Row {idx}: ts_str={repr(ts_str)}, symbol={symbol}")
            try:
                t_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).date()
                t_date_str = t_dt.strftime("%Y%m%d")
                print(f"  Parsed successfully: {t_date_str}")
            except Exception as e:
                print(f"  FAILED to parse: {e}")

if __name__ == "__main__":
    asyncio.run(main())
