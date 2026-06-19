"""Backtest-related HTTP API: files, strategies, metadata, run/cancel."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Body, Query, status

from src.utils.files import backtest_duration, inspect_parquet_to_dict, list_files, list_strategies
from src.services.backtest import BacktestService
from src.api.schemas.backtest import RunBacktestRequest


router = APIRouter()


@router.get(
    "/api/files",
    tags=["Backtest Data"],
    summary="List Backtest Data Files",
    description="Scan download/ and data/ directories to list available DBN and Parquet files for backtesting.",
)
def api_files() -> List[Dict[str, Any]]:
    return [f.__dict__ for f in list_files()]


@router.get(
    "/api/backtest/strategies",
    tags=["Backtest Strategies"],
    summary="List Strategy Classes",
    description="Retrieve all compiled C++ strategy classes that can be selected for backtesting.",
)
def api_backtest_strategies() -> Dict[str, Any]:
    import json
    return json.loads(list_strategies())


@router.get(
    "/api/file_info",
    tags=["Backtest Data"],
    summary="Get Parquet File Info",
    description="Get metadata of a specific Parquet file, including row count, date coverage, and unique timestamp density.",
)
def api_file_info(
    path: str = Query(..., description="Relative path to .parquet file"),
) -> Dict[str, Any]:
    return inspect_parquet_to_dict(path)


@router.get(
    "/api/backtest_duration",
    tags=["Backtest Data"],
    summary="Get Symbols Date Range",
    description="Get calendar duration (covered days and min/max date ranges) grouped by asset symbols.",
)
def api_backtest_duration() -> Dict[str, Any]:
    return backtest_duration()


@router.post(
    "/api/run_backtest",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Backtest Execution"],
    summary="Run Backtest Job",
    description="Submit a backtest configuration to the asynchronous task queue. Runs non-blocking and returns a tracking job ID.",
)
async def api_run_backtest(
    request: RunBacktestRequest = Body(...),
) -> Dict[str, Any]:
    return await BacktestService.run_backtest(request.model_dump())


@router.post(
    "/api/backtest/cancel",
    tags=["Backtest Execution"],
    summary="Cancel Backtest Job",
    description="Send a cancellation signal to stop the currently running C++ backtest process.",
)
async def api_backtest_cancel() -> Dict[str, Any]:
    return await BacktestService.cancel_backtest()
