"""Backtest-related HTTP API: files, strategies, metadata, run/cancel."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Body, Query, status

from src.utils.files import backtest_duration, inspect_parquet_to_dict, list_files, list_strategies
from src.services.backtest import BacktestService


router = APIRouter()


@router.get("/api/files")
def api_files() -> List[Dict[str, Any]]:
    """List .dbn and .parquet under download/ and data/."""
    return [f.__dict__ for f in list_files()]


@router.get("/api/backtest/strategies")
def api_backtest_strategies() -> Dict[str, Any]:
    """List C++ strategy classes for backtest dropdown."""
    import json

    return json.loads(list_strategies())


@router.get("/api/file_info")
def api_file_info(
    path: str = Query(..., description="Relative path to .parquet"),
) -> Dict[str, Any]:
    """Parquet meta: row_count, ts_start, ts_end, unique_ts_count."""
    return inspect_parquet_to_dict(path)


@router.get("/api/backtest_duration")
def api_backtest_duration() -> Dict[str, Any]:
    """Backtest duration by symbol (covered_days, date range)."""
    return backtest_duration()


@router.post("/api/run_backtest", status_code=status.HTTP_202_ACCEPTED)
async def api_run_backtest(
    request: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    """Run backtest (non-blocking); enqueues task and returns job ID."""
    return await BacktestService.run_backtest(request)


@router.post("/api/backtest/cancel")
async def api_backtest_cancel() -> Dict[str, Any]:
    """Cancel running C++ backtest (if any)."""
    return await BacktestService.cancel_backtest()
