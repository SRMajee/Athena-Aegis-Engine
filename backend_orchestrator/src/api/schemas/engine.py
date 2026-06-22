from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AddStrategyRequest(BaseModel):
    strategy_class: str = Field(..., description="C++ Strategy class name to instantiate")
    portfolio_name: str = Field(..., description="Target portfolio to deploy the strategy to")
    setting: Optional[Dict[str, Any]] = Field(None, description="Custom strategy configurations and parameters")


class RestoreStrategyRequest(BaseModel):
    strategy_name: str = Field(..., description="Unique strategy identifier to restore")
    portfolio_name: Optional[str] = Field(None, description="Portfolio to associate the restored strategy with")
    setting: Optional[Dict[str, Any]] = Field(None, description="Custom parameters to apply during restoration")


# Response schemas for Live Engine endpoints
class ConnectGatewayResponse(BaseModel):
    status: str = Field("ok", description="Status of the gateway connection request")
    details: Optional[str] = Field(None, description="Connection diagnostic details")


class DisconnectGatewayResponse(BaseModel):
    status: str = Field("ok", description="Status of the gateway disconnect request")


class GatewayStatusResponse(BaseModel):
    connected: bool = Field(..., description="Brokerage gateway connection status")
    broker: str = Field("paper", description="Active broker environment name (e.g. paper, live, alpaca)")


class MarketStatusResponse(BaseModel):
    active: bool = Field(..., description="Active state of live market data subscriptions")
    subscribed_symbols: List[str] = Field(..., description="List of currently subscribed tickers")


class StartMarketResponse(BaseModel):
    status: str = Field("ok", description="Status of starting the market data stream")


class StopMarketResponse(BaseModel):
    status: str = Field("ok", description="Status of stopping the market data stream")


class StrategyListResponse(BaseModel):
    strategies: List[Dict[str, Any]] = Field(..., description="Detailed statuses of all loaded strategy instances")


class StrategyUpdatesResponse(BaseModel):
    updates: List[Dict[str, Any]] = Field(..., description="Recent real-time execution events or metrics from active strategies")


class ClearStrategyUpdatesResponse(BaseModel):
    status: str = Field("ok", description="Status of clearing the update buffer")


class StrategyClassesResponse(BaseModel):
    strategy_classes: List[str] = Field(..., description="List of registered C++ strategy class names available for deployment")


class StrategySettingsResponse(BaseModel):
    default_settings: Dict[str, Any] = Field(..., description="JSON-serialized default configuration schemas for the requested strategy class")


class PortfoliosResponse(BaseModel):
    portfolios: Dict[str, Any] = Field(..., description="Active portfolios metadata including weights and parameters")


class RemovedStrategiesResponse(BaseModel):
    removed_strategies: List[str] = Field(..., description="IDs of strategies that have been stopped and removed from the runtime")


class StrategyActionResponse(BaseModel):
    status: str = Field("ok", description="Status of the requested strategy action")
    strategy_name: str = Field(..., description="Name of the affected strategy")


class HoldingsResponse(BaseModel):
    holdings: List[Dict[str, Any]] = Field(..., description="List of active positions, including strike, ticker, type, and delta size")


class OrdersTradesResponse(BaseModel):
    orders: List[Dict[str, Any]] = Field(..., description="Active resting or pending order details")
    trades: List[Dict[str, Any]] = Field(..., description="Completed trade execution records")


class PortfolioNamesResponse(BaseModel):
    portfolios: List[str] = Field(..., description="List of registered portfolio names")


class LogEntry(BaseModel):
    timestamp: str = Field(..., description="Timestamp of the log entry")
    level: str = Field(..., description="Log level (INFO, WARNING, ERROR, DEBUG)")
    message: str = Field(..., description="Diagnostic text message")


class LogListResponse(BaseModel):
    logs: List[LogEntry] = Field(..., description="Log entries loaded from the buffer")


class ClearLogsResponse(BaseModel):
    status: str = Field("ok", description="Status of clearing the logs buffer")
