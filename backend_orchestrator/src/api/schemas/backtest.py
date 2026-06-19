from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class BacktestFileEntry(BaseModel):
    name: str = Field(..., description="File name with extension")
    path: str = Field(..., description="Relative path from workspace root")
    size_bytes: int = Field(..., description="File size in bytes")
    is_dir: bool = Field(..., description="Whether the entry is a directory")


class ParquetFileInfoResponse(BaseModel):
    row_count: int = Field(..., description="Total number of rows in the parquet file")
    ts_start: Optional[str] = Field(None, description="Start timestamp of the data")
    ts_end: Optional[str] = Field(None, description="End timestamp of the data")
    unique_ts_count: int = Field(..., description="Count of unique timestamps (e.g., daily snapshots vs tick bars)")


class BacktestDurationEntry(BaseModel):
    covered_days: int = Field(..., description="Total calendar days spanned by the data")
    date_range: List[str] = Field(..., description="List of date strings covering the data range")


class RunBacktestRequest(BaseModel):
    parquet: str = Field("SPY", description="Asset ticker/symbol to backtest")
    strategy: str = Field("StraddleTestStrategy", description="Name of the strategy class to run")
    fee_rate: float = Field(0.35, description="Transaction fee rate per option contract")
    slippage_bps: float = Field(5.0, description="Assumed execution slippage in basis points")
    risk_free_rate: float = Field(0.05, description="Annualized risk-free rate used for Greeks calculations")
    iv_price_mode: str = Field("mid", description="Implied volatility source pricing mode (mid, bid, ask)")
    strategy_setting: Dict[str, Any] = Field(default_factory=dict, description="Custom configuration key-values for the strategy")
    start_date: str = Field("2010-01-04", description="Start date of backtest period (YYYY-MM-DD)")
    end_date: str = Field("2010-01-10", description="End date of backtest period (YYYY-MM-DD)")
    model_ids: List[str] = Field(default=["deep_hedge_ffnn"], description="IDs of deep hedging ML models to evaluate")
    correlation_id: Optional[str] = Field(None, description="Client-defined ID to correlate logs and websocket updates")


class RunBacktestResponse(BaseModel):
    status: str = Field("ok", description="Status of the task submission")
    job_id: str = Field(..., description="Unique task queue ID for tracking execution")
    correlation_id: Optional[str] = Field(None, description="Associated correlation ID")


class CancelBacktestResponse(BaseModel):
    status: str = Field("ok", description="Status of the cancel request")
    message: str = Field(..., description="Details regarding cancellation progress")
