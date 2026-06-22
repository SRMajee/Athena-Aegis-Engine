from __future__ import annotations

import os
import dotenv
from typing import Any, Dict, List, Optional, Sequence, Tuple
from datetime import datetime, timezone
from uuid import UUID, uuid4
import sqlalchemy as sa
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import SQLModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

# Load .env file
dotenv.load_dotenv()

try:
    import psycopg2  # type: ignore[import]
except Exception:  # pragma: no cover - optional dependency
    psycopg2 = None


class DBError(Exception):
    """Domain-specific error for database access issues."""


# Swap URL scheme dynamically
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

async_engine = None
async_session_maker = None

if DATABASE_URL:
    async_engine = create_async_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        echo=False
    )
    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )


async def get_async_session():
    if async_session_maker is None:
        raise DBError("Database connection not configured")
    async with async_session_maker() as session:
        yield session


# SQLModel schemas for Deep Hedging & Execution Platform
class Strategy(SQLModel, table=True):
    __tablename__: str = "strategy"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    instrument: str
    parameters: dict = Field(default_factory=dict, sa_column=Column(JSONB))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BacktestJob(SQLModel, table=True):
    __tablename__: str = "backtest_job"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    strategy_id: UUID = Field(foreign_key="strategy.id")
    status: str = Field(default="PENDING")
    correlation_id: str = Field(unique=True, index=True)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = Field(default=None)
    summary: Optional[dict] = Field(default=None, sa_column=Column(JSONB))


class ModelRegistry(SQLModel, table=True):
    __tablename__: str = "model_registry"

    id: str = Field(primary_key=True)
    torchscript_path: str
    training_run_id: str
    input_shape: List[int] = Field(sa_column=Column(JSONB))
    validation_cvar: float
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TickArchive(SQLModel, table=True):
    __tablename__: str = "tick_archive"

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: UUID = Field(foreign_key="backtest_job.id")
    tick_timestamp_ns: int = Field(sa_column=Column(sa.BigInteger))
    spot: float
    iv: float
    tick_metadata: Optional[dict] = Field(default=None, sa_column=Column("metadata", JSONB))


class RiskSnapshot(SQLModel, table=True):
    __tablename__: str = "risk_snapshot"

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: UUID = Field(foreign_key="backtest_job.id")
    model_id: str = Field(foreign_key="model_registry.id")
    tick_idx: int
    delta: float
    gamma: float
    cvar_95: float
    cvar_99: float
    pnl: float


def get_connection():
    """PostgreSQL read-only connection (DATABASE_URL)."""
    if psycopg2 is None:
        raise DBError("psycopg2 is not installed on backend")
    conninfo = os.environ.get("DATABASE_URL", "").strip()
    if not conninfo:
        raise DBError("DATABASE_URL not configured")
    # Use original unmodified postgresql URL for psycopg2 connection
    original_url = os.environ.get("DATABASE_URL", "").strip()
    return psycopg2.connect(original_url)


def fetch_orders_trades_raw(
    strategy: Optional[str],
    limit: int,
    record_type: Optional[str] = None,
) -> Tuple[List[str], Sequence[Tuple[Any, ...]], int, float, Dict[str, int], Dict[str, float]]:
    """
    Low-level query for historical orders & trades.

    Returns a tuple of:
    - strategies: distinct strategy_name list (for filters)
    - rows: raw rows from the unified orders/trades query
    - total_count: total matching records in database
    - total_volume: sum of volume of matching records
    - daily_trades: date -> trade count
    - daily_volume: date -> sum of trade volume
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Distinct strategy names
            cur.execute(
                """
                SELECT DISTINCT strategy_name FROM orders
                UNION
                SELECT DISTINCT strategy_name FROM trades
                ORDER BY strategy_name
                """
            )
            strategies = [row[0] for row in cur.fetchall() if row[0]]

            params: List[Any] = []
            orders_where: List[str] = []
            trades_where: List[str] = []

            if strategy:
                orders_where.append("strategy_name = %s")
                trades_where.append("strategy_name = %s")

            orders_sql = """
                SELECT
                    'Order' AS record_type,
                    timestamp,
                    strategy_name,
                    orderid,
                    symbol,
                    direction,
                    price,
                    volume,
                    traded,
                    status
                FROM orders
            """
            trades_sql = """
                SELECT
                    'Trade' AS record_type,
                    timestamp,
                    strategy_name,
                    tradeid,
                    symbol,
                    direction,
                    price,
                    volume,
                    NULL::double precision AS traded,
                    NULL::text AS status
                FROM trades
            """

            if orders_where:
                orders_sql += " WHERE " + " AND ".join(orders_where)
            if trades_where:
                trades_sql += " WHERE " + " AND ".join(trades_where)

            # Get total count and volume
            total_count = 0
            total_volume = 0.0
            daily_trades: Dict[str, int] = {}
            daily_volume: Dict[str, float] = {}

            if record_type == "Order":
                count_sql = "SELECT COUNT(*), COALESCE(SUM(volume), 0) FROM orders"
                count_params = []
                if strategy:
                    count_sql += " WHERE strategy_name = %s"
                    count_params.append(strategy)
                cur.execute(count_sql, count_params)
                row = cur.fetchone()
                if row:
                    total_count, total_volume = int(row[0]), float(row[1])
            elif record_type == "Trade":
                count_sql = "SELECT COUNT(*), COALESCE(SUM(volume), 0) FROM trades"
                count_params = []
                if strategy:
                    count_sql += " WHERE strategy_name = %s"
                    count_params.append(strategy)
                cur.execute(count_sql, count_params)
                row = cur.fetchone()
                if row:
                    total_count, total_volume = int(row[0]), float(row[1])
                
                # Fetch daily aggregations
                daily_sql = """
                    SELECT SUBSTRING(timestamp, 1, 10) AS trade_date, COUNT(*), COALESCE(SUM(volume), 0)
                    FROM trades
                    {where}
                    GROUP BY SUBSTRING(timestamp, 1, 10)
                    ORDER BY trade_date
                """
                where_clause = ""
                daily_params = []
                if strategy:
                    where_clause = "WHERE strategy_name = %s"
                    daily_params.append(strategy)
                cur.execute(daily_sql.format(where=where_clause), daily_params)
                for r in cur.fetchall():
                    d_str, count, vol = r[0], int(r[1]), float(r[2])
                    if d_str:
                        daily_trades[d_str] = count
                        daily_volume[d_str] = vol
            else:
                count_sql_orders = "SELECT COUNT(*), COALESCE(SUM(volume), 0) FROM orders"
                count_sql_trades = "SELECT COUNT(*), COALESCE(SUM(volume), 0) FROM trades"
                params_orders = []
                params_trades = []
                if strategy:
                    count_sql_orders += " WHERE strategy_name = %s"
                    count_sql_trades += " WHERE strategy_name = %s"
                    params_orders.append(strategy)
                    params_trades.append(strategy)
                cur.execute(count_sql_orders, params_orders)
                r_o = cur.fetchone()
                c_o, v_o = (int(r_o[0]), float(r_o[1])) if r_o else (0, 0.0)

                cur.execute(count_sql_trades, params_trades)
                r_t = cur.fetchone()
                c_t, v_t = (int(r_t[0]), float(r_t[1])) if r_t else (0, 0.0)

                total_count = c_o + c_t
                total_volume = v_o + v_t

            if record_type == "Order":
                union_sql = f"""
                    {orders_sql}
                    ORDER BY timestamp DESC
                    LIMIT %s
                """
                if strategy:
                    params.append(strategy)
                params.append(limit)
            elif record_type == "Trade":
                union_sql = f"""
                    {trades_sql}
                    ORDER BY timestamp DESC
                    LIMIT %s
                """
                if strategy:
                    params.append(strategy)
                params.append(limit)
            else:
                union_sql = f"""
                    {orders_sql}
                    UNION ALL
                    {trades_sql}
                    ORDER BY timestamp DESC
                    LIMIT %s
                """
                if strategy:
                    params.append(strategy)
                    params.append(strategy)
                params.append(limit)

            cur.execute(union_sql, params)
            rows = cur.fetchall()

        return strategies, rows, total_count, total_volume, daily_trades, daily_volume
    except Exception as exc:  # pragma: no cover - simple wrapper
        raise DBError(f"Failed to fetch orders/trades: {exc}") from exc
    finally:
        conn.close()


def fetch_contracts_summary() -> Dict[str, Any]:
    """Summary of contract_equity and contract_option (equity/option totals + rows)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Equity
            cur.execute("SELECT COUNT(*) FROM contract_equity")
            equity_total_row = cur.fetchone()
            equity_total = int(equity_total_row[0]) if equity_total_row else 0

            cur.execute(
                """
                SELECT symbol, exchange, product, size, pricetick, gateway_name
                FROM contract_equity
                ORDER BY symbol
                LIMIT 50
                """
            )
            equity_rows = [
                {
                    "symbol": row[0],
                    "exchange": row[1],
                    "product": row[2],
                    "size": float(row[3]) if row[3] is not None else None,
                    "pricetick": float(row[4]) if row[4] is not None else None,
                    "gateway_name": row[5],
                }
                for row in cur.fetchall()
            ]

            # Option totals + chains
            cur.execute(
                """
                SELECT
                    COUNT(*) AS cnt,
                    COUNT(
                        DISTINCT
                        split_part(symbol, '-', 1) || '_' || split_part(symbol, '-', 2)
                    ) AS chains
                FROM contract_option
                """
            )
            opt_row = cur.fetchone()
            option_total = int(opt_row[0]) if opt_row and opt_row[0] is not None else 0
            option_chains = int(opt_row[1]) if opt_row and opt_row[1] is not None else 0

            # Per-chain (DTE, strike range)
            cur.execute(
                """
                WITH opt AS (
                    SELECT
                        split_part(symbol, '-', 1) || '_' || split_part(symbol, '-', 2) AS chain_symbol,
                        expiry,
                        type,
                        strike,
                        underlying
                    FROM contract_option
                )
                SELECT
                    chain_symbol,
                    MIN(DATE(expiry)) AS expiry_date,
                    GREATEST(0, MIN(DATE(expiry) - CURRENT_DATE)) AS dte,
                    COUNT(*) FILTER (WHERE type = 'CALL') AS calls,
                    COUNT(*) FILTER (WHERE type = 'PUT') AS puts,
                    MIN(strike) AS strike_min,
                    MAX(strike) AS strike_max,
                    MIN(underlying) AS underlying_sample
                FROM opt
                GROUP BY chain_symbol
                ORDER BY expiry_date, chain_symbol
                LIMIT 100
                """
            )
            option_rows = [
                {
                    "chain": row[0],
                    "dte": int(row[2]) if row[2] is not None else None,
                    "calls": int(row[3]) if row[3] is not None else 0,
                    "puts": int(row[4]) if row[4] is not None else 0,
                    "strike_min": float(row[5]) if row[5] is not None else None,
                    "strike_max": float(row[6]) if row[6] is not None else None,
                    "underlying": row[7],
                }
                for row in cur.fetchall()
            ]

        return {
            "equity": {
                "total": equity_total,
                "rows": equity_rows,
            },
            "option": {
                "total": option_total,
                "chains": option_chains,
                "rows": option_rows,
            },
        }
    except Exception as exc:  # pragma: no cover - simple wrapper
        raise DBError(f"Failed to fetch contracts summary: {exc}") from exc
    finally:
        conn.close()

