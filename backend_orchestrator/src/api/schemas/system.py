from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class BackendStatus(BaseModel):
    status: str = Field("running", description="Status of the FastAPI gateway")


class LiveEngineStatus(BaseModel):
    gateway_connected: bool = Field(..., description="Whether the trading gateway is connected")
    market_data_active: bool = Field(..., description="Whether active market data subscriptions are running")
    strategies_loaded: int = Field(..., description="Count of strategies currently loaded")
    strategies_active: int = Field(..., description="Count of strategies currently running")


class SystemStatusResponse(BaseModel):
    backend: BackendStatus = Field(..., description="FastAPI web application state")
    live: Dict[str, Any] = Field(..., description="Raw state fields of the live execution client")


class LiveRestartResponse(BaseModel):
    status: str = Field("ok", description="Status of the soft restart action")
    disconnect: Dict[str, Any] = Field(..., description="Result summary from the disconnect phase")
    connect: Dict[str, Any] = Field(..., description="Result summary from the reconnect phase")


class DatabaseOrdersTradesResponse(BaseModel):
    strategy_name: Optional[str] = Field(None, description="Filtered strategy name")
    record_type: Optional[str] = Field(None, description="Filtered record type (Order/Trade)")
    records: List[Dict[str, Any]] = Field(..., description="List of historical records loaded from the DB")


class DatabaseContractsOverview(BaseModel):
    total_contracts: int = Field(..., description="Total option/equity contracts registered in the DB")
    contract_types: Dict[str, int] = Field(..., description="Summary of counts by contract type")
