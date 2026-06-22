"""System-level APIs: health, live restart, DB views."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Query

from src.infra.state import AppState
from src.services.system import (
    get_contracts_overview_from_db,
    get_orders_trades_from_db,
)


router = APIRouter()


@router.get(
    "/api/system/status",
    tags=["System - Health & Status"],
    summary="Get System Health Status",
    description="Check health of FastAPI application and query connected state, subscription status, and strategy counts of the C++ execution engine.",
)
def api_system_status() -> Dict[str, Any]:
    return {
        "backend": {"status": "running"},
        "live": AppState.live.live_status,
    }


@router.post(
    "/api/system/restart_live",
    tags=["System - Health & Status"],
    summary="Soft Restart Live Client",
    description="Trigger a soft restart of the C++ live connection client: disconnects from the current gateway session and re-establishes connections.",
)
async def api_restart_live() -> Dict[str, Any]:
    if AppState.live.live_client is None:
        return {"status": "error", "error": "live_client not initialized"}

    disc = await AppState.live.live_client.disconnect_gateway()
    conn = await AppState.live.live_client.connect_gateway()
    return {"status": "ok", "disconnect": disc, "connect": conn}


@router.get(
    "/api/orders-trades/db",
    tags=["System - Historical Database Views"],
    summary="Query Historical Orders & Trades",
    description="Retrieve historical order entries and trade execution records stored in the PostgreSQL database. Supports optional strategy filters.",
)
async def api_orders_trades_db(
    strategy: Optional[str] = Query(None, description="Filter records by strategy name"),
    record_type: Optional[str] = Query(
        None, description="Filter by type (Order, Trade, or omit for both)"
    ),
    limit: int = Query(100, ge=1, le=5000, description="Maximum count of records to fetch"),
) -> Dict[str, Any]:
    return await get_orders_trades_from_db(
        strategy=strategy,
        record_type=record_type,
        limit=limit,
    )


@router.get(
    "/api/database/contracts",
    tags=["System - Historical Database Views"],
    summary="Get Database Contracts Summary",
    description="Query PostgreSQL to retrieve a consolidated overview of registered equity and options contracts and total row counts.",
)
async def api_database_contracts() -> Dict[str, Any]:
    return await get_contracts_overview_from_db()
