"""Unified engine API router: gateway, strategies, holdings, orders-trades, logs."""

from fastapi import APIRouter, Query

from src.api.schemas.engine import AddStrategyRequest, RestoreStrategyRequest
from src.services.main import MainService
from src.services.strategy import StrategyService


router = APIRouter()


@router.post("/api/gateway/connect")
async def connect_gateway() -> dict:
    return await MainService.connect_gateway()


@router.post("/api/gateway/disconnect")
async def disconnect_gateway() -> dict:
    return await MainService.disconnect_gateway()


@router.get("/api/gateway/status")
async def get_gateway_status() -> dict:
    return await MainService.get_gateway_status()


@router.get("/api/market/status")
async def get_market_status() -> dict:
    return await MainService.get_market_status()


@router.post("/api/market/start")
async def start_market() -> dict:
    return await MainService.start_market_data()


@router.post("/api/market/stop")
async def stop_market() -> dict:
    return await MainService.stop_market_data()


@router.get("/api/strategies")
async def list_strategies() -> dict:
    return await StrategyService.list_strategies()


@router.get("/api/strategies/updates")
def get_strategy_updates() -> dict:
    return StrategyService.get_strategy_updates()


@router.get("/api/strategies/updates/clear")
def clear_strategy_updates() -> dict:
    return StrategyService.clear_strategy_updates()


@router.get("/api/strategies/meta/strategy-classes")
async def get_strategy_classes() -> dict:
    return await StrategyService.get_strategy_classes()


@router.get("/api/strategies/meta/settings")
async def get_strategy_class_settings(strategy_class: str = Query(..., alias="class")) -> dict:
    """Default settings for strategy class (strategy_config.json)."""
    return await StrategyService.get_strategy_class_defaults(strategy_class)


@router.get("/api/strategies/meta/portfolios")
async def get_portfolios() -> dict:
    return await StrategyService.get_portfolios_meta()


@router.get("/api/strategies/meta/removed-strategies")
async def get_removed_strategies() -> dict:
    return await StrategyService.get_removed_strategies()


@router.post("/api/strategies")
async def add_strategy(req: AddStrategyRequest) -> dict:
    return await StrategyService.add_strategy(req)


@router.post("/api/strategies/restore")
async def restore_strategy(req: RestoreStrategyRequest) -> dict:
    return await StrategyService.restore_strategy(req)


@router.post("/api/strategies/{strategy_name}/init")
async def init_strategy(strategy_name: str) -> dict:
    return await StrategyService.init_strategy(strategy_name)


@router.post("/api/strategies/{strategy_name}/start")
async def start_strategy(strategy_name: str) -> dict:
    return await StrategyService.start_strategy(strategy_name)


@router.post("/api/strategies/{strategy_name}/stop")
async def stop_strategy(strategy_name: str) -> dict:
    return await StrategyService.stop_strategy(strategy_name)


@router.delete("/api/strategies/{strategy_name}/remove")
async def remove_strategy(strategy_name: str) -> dict:
    return await StrategyService.remove_strategy(strategy_name)


@router.delete("/api/strategies/{strategy_name}/delete")
async def delete_strategy(strategy_name: str) -> dict:
    return await StrategyService.delete_strategy(strategy_name)


@router.get("/api/strategies/holdings")
async def get_strategy_holdings() -> dict:
    return await StrategyService.get_strategy_holdings()


@router.get("/api/orders-trades")
async def get_orders_and_trades() -> dict:
    return await MainService.get_orders_and_trades()


@router.get("/api/data/portfolios")
async def get_portfolio_names() -> dict:
    return await MainService.get_portfolio_names()


@router.get("/logs")
def get_logs(limit: int = 200) -> dict:
    return MainService.get_logs(limit)


@router.get("/api/logs")
def get_logs_api() -> dict:
    return MainService.get_logs_api()


@router.post("/api/logs/clear")
def clear_logs() -> dict:
    """Clear log buffer (e.g. Clear button)."""
    return MainService.clear_logs()
