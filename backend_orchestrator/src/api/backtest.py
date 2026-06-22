"""Backtest-related HTTP API: files, strategies, metadata, run/cancel."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Body, Query, status, HTTPException
from fastapi.responses import FileResponse
import os

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


@router.get(
    "/api/backtest/jobs/{job_id}/report",
    tags=["Backtest Execution"],
    summary="Get Backtest PDF Report",
    description="Retrieve the PDF strategy report for a completed backtest job. If the report doesn't exist yet, it will be generated on the fly.",
)
async def api_get_backtest_report(job_id: str):
    workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    pdf_path = os.path.abspath(os.path.join(workspace_root, "data", "reports", f"{job_id}.pdf"))

    if not os.path.exists(pdf_path):
        from src.infra.task_queue import generate_report
        from src.infra.db import async_session_maker, BacktestJob
        from uuid import UUID

        async with async_session_maker() as session:
            job = await session.get(BacktestJob, UUID(job_id))
            if not job:
                raise HTTPException(status_code=404, detail="Backtest job not found")
            if job.status != "COMPLETE":
                raise HTTPException(status_code=400, detail=f"Backtest job report cannot be generated because job status is {job.status}")
        
        try:
            generated_path = await generate_report(None, job_id)
            if not generated_path or not os.path.exists(generated_path):
                raise HTTPException(status_code=500, detail="Failed to generate PDF report")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"strategy_report_{job_id}.pdf"
    )
