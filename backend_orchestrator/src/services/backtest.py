"""Backtest service: parameter validation, process management, and C++ runner bridge."""

from __future__ import annotations

import os
from uuid import uuid4, UUID
from typing import Any, Dict

from src.infra.state import AppState
from src.infra.db import async_session_maker, Strategy, BacktestJob

DEFAULT_FEE_RATE = 0.35
DEFAULT_RISK_FREE_RATE = 0.05
DEFAULT_IV_PRICE_MODE = "mid"


class BacktestService:
    """High-level backtest operations."""

    @staticmethod
    async def run_backtest(request: Dict[str, Any]) -> Dict[str, Any]:
        parquet = request.get("parquet", "")
        strategy = request.get("strategy", "")
        strategy_setting = request.get("strategy_setting", None)
        iv_price_mode = str(request.get("iv_price_mode", DEFAULT_IV_PRICE_MODE) or DEFAULT_IV_PRICE_MODE).lower()
        start_date = request.get("start_date")  # YYYY-MM-DD format
        end_date = request.get("end_date")  # YYYY-MM-DD format
        try:
            fee_rate = float(request.get("fee_rate", DEFAULT_FEE_RATE) or DEFAULT_FEE_RATE)
            slippage_bps = float(request.get("slippage_bps", 5.0) or 5.0)
            risk_free_rate = float(request.get("risk_free_rate", DEFAULT_RISK_FREE_RATE) or DEFAULT_RISK_FREE_RATE)
        except (TypeError, ValueError):
            return {"status": "error", "error": "fee_rate, slippage_bps and risk_free_rate must be numbers"}
        if iv_price_mode not in {"mid", "bid", "ask"}:
            return {"status": "error", "error": "iv_price_mode must be mid, bid, or ask"}
        if fee_rate < 0:
            return {"status": "error", "error": "fee_rate must be >= 0"}
        if slippage_bps < 0:
            slippage_bps = 0.0
        if not parquet or not strategy:
            return {"status": "error", "error": "Missing required fields: parquet, strategy"}
        if not start_date or not end_date:
            return {"status": "error", "error": "Missing required fields: start_date, end_date"}

        correlation_id = str(uuid4())

        # 1. Create Strategy and BacktestJob records in PostgreSQL
        try:
            async with async_session_maker() as session:
                db_strategy = Strategy(
                    name=strategy,
                    instrument=parquet,
                    parameters=strategy_setting or {}
                )
                session.add(db_strategy)
                await session.flush()  # Populate db_strategy.id

                db_job = BacktestJob(
                    id=UUID(correlation_id),
                    strategy_id=db_strategy.id,
                    status="PENDING",
                    correlation_id=correlation_id
                )
                session.add(db_job)

                # Clear old orders and trades for this strategy to prevent stale calculations
                import sqlalchemy as sa
                await session.execute(
                    sa.text("DELETE FROM trades WHERE strategy_name = :name"),
                    {"name": strategy}
                )
                await session.execute(
                    sa.text("DELETE FROM orders WHERE strategy_name = :name"),
                    {"name": strategy}
                )

                await session.commit()
        except Exception as e:
            return {"status": "error", "error": f"Failed to persist job metadata: {e}"}

        # 2. Enqueue the backtest job in the ARQ Redis task queue
        job_payload = {
            "parquet": parquet,
            "strategy": strategy,
            "fee_rate": fee_rate,
            "slippage_bps": slippage_bps,
            "risk_free_rate": risk_free_rate,
            "iv_price_mode": iv_price_mode,
            "strategy_setting": strategy_setting or {},
            "start_date": start_date,
            "end_date": end_date,
            "correlation_id": correlation_id
        }

        try:
            arq_redis = getattr(AppState, "arq_redis", None)
            if arq_redis is None:
                return {"status": "error", "error": "ARQ Redis queue not initialized"}
            
            await arq_redis.enqueue_job(
                "run_backtest_job",
                job_payload,
                _job_id=correlation_id
            )
            # Track the active job ID for cancellations
            AppState.backtest.active_job_id = correlation_id
        except Exception as e:
            return {"status": "error", "error": f"Failed to enqueue backtest task: {e}"}

        # Return 202 Accepted equivalent
        return {"status": "ok", "job_id": correlation_id}

    @staticmethod
    async def cancel_backtest() -> Dict[str, Any]:
        """Cancel running C++ backtest (if any)."""
        job_id = getattr(AppState.backtest, "active_job_id", None)
        if job_id:
            redis_client = getattr(AppState, "redis", None)
            if redis_client:
                # Set a cancel signal in Redis with 60 second expiration
                await redis_client.set(f"job_cancel:{job_id}", "1", ex=60)
            return {"status": "ok", "message": f"Cancel signal sent for job {job_id}"}
        return {"status": "ok", "message": "No active backtest job found"}
