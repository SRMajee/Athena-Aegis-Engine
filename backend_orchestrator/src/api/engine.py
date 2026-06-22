"""Unified engine API router: gateway, strategies, holdings, orders-trades, logs."""

import os
import shutil
from fastapi import APIRouter, Query, UploadFile, File, HTTPException

from src.api.schemas.engine import AddStrategyRequest, RestoreStrategyRequest
from src.services.main import MainService
from src.services.strategy import StrategyService

router = APIRouter()


# --- Live Engine - Gateway ---
@router.post(
    "/api/gateway/connect",
    tags=["Live Engine - Gateway"],
    summary="Connect Gateway",
    description="Establish active connection between the execution runtime and the live brokerage gateway.",
)
async def connect_gateway() -> dict:
    return await MainService.connect_gateway()


@router.post(
    "/api/gateway/disconnect",
    tags=["Live Engine - Gateway"],
    summary="Disconnect Gateway",
    description="Gracefully terminate connection to the live brokerage gateway.",
)
async def disconnect_gateway() -> dict:
    return await MainService.disconnect_gateway()


@router.get(
    "/api/gateway/status",
    tags=["Live Engine - Gateway"],
    summary="Get Gateway Connection Status",
    description="Query current connection status and active broker configuration of the gateway.",
)
async def get_gateway_status() -> dict:
    return await MainService.get_gateway_status()


# --- Live Engine - Market Data ---
@router.get(
    "/api/market/status",
    tags=["Live Engine - Market Data"],
    summary="Get Market Data Stream Status",
    description="Check whether market data streams are running and list current symbol subscriptions.",
)
async def get_market_status() -> dict:
    return await MainService.get_market_status()


@router.post(
    "/api/market/start",
    tags=["Live Engine - Market Data"],
    summary="Start Market Data Stream",
    description="Activate real-time market data ticks and order-book updates subscription stream.",
)
async def start_market() -> dict:
    return await MainService.start_market_data()


@router.post(
    "/api/market/stop",
    tags=["Live Engine - Market Data"],
    summary="Stop Market Data Stream",
    description="Halt the active real-time market data subscription feed.",
)
async def stop_market() -> dict:
    return await MainService.stop_market_data()


# --- Live Engine - Strategy Management ---
@router.get(
    "/api/strategies",
    tags=["Live Engine - Strategy Management"],
    summary="List Strategies",
    description="List all currently instantiated strategy configurations and their runtime states.",
)
async def list_strategies() -> dict:
    return await StrategyService.list_strategies()


@router.get(
    "/api/strategies/updates",
    tags=["Live Engine - Strategy Management"],
    summary="Get Strategy Updates",
    description="Query real-time metrics and state-change events emitted from running strategies.",
)
def get_strategy_updates() -> dict:
    return StrategyService.get_strategy_updates()


@router.get(
    "/api/strategies/updates/clear",
    tags=["Live Engine - Strategy Management"],
    summary="Clear Strategy Updates Buffer",
    description="Reset the strategy real-time update buffer.",
)
def clear_strategy_updates() -> dict:
    return StrategyService.clear_strategy_updates()


@router.get(
    "/api/strategies/meta/strategy-classes",
    tags=["Live Engine - Strategy Management"],
    summary="Get Available Strategy Classes",
    description="Get list of all compiled C++ strategy classes available for live deployment.",
)
async def get_strategy_classes() -> dict:
    return await StrategyService.get_strategy_classes()


@router.get(
    "/api/strategies/meta/settings",
    tags=["Live Engine - Strategy Management"],
    summary="Get Strategy Settings Schema",
    description="Retrieve default configuration key-value structures for a given strategy class.",
)
async def get_strategy_class_settings(strategy_class: str = Query(..., alias="class", description="Name of the strategy class")) -> dict:
    return await StrategyService.get_strategy_class_defaults(strategy_class)


@router.get(
    "/api/strategies/meta/portfolios",
    tags=["Live Engine - Strategy Management"],
    summary="Get Portfolio Parameters",
    description="Retrieve active deployment portfolios metadata including allocation weights.",
)
async def get_portfolios() -> dict:
    return await StrategyService.get_portfolios_meta()


@router.get(
    "/api/strategies/meta/removed-strategies",
    tags=["Live Engine - Strategy Management"],
    summary="Get Removed Strategies List",
    description="Get IDs of strategies that were instantiated and subsequently removed from the session.",
)
async def get_removed_strategies() -> dict:
    return await StrategyService.get_removed_strategies()


@router.post(
    "/api/strategies",
    tags=["Live Engine - Strategy Management"],
    summary="Add Strategy",
    description="Instantiate a C++ strategy class and associate it with a specific portfolio.",
)
async def add_strategy(req: AddStrategyRequest) -> dict:
    return await StrategyService.add_strategy(req)


@router.post(
    "/api/strategies/restore",
    tags=["Live Engine - Strategy Management"],
    summary="Restore Strategy",
    description="Restore configuration parameters and states of a previously removed strategy.",
)
async def restore_strategy(req: RestoreStrategyRequest) -> dict:
    return await StrategyService.restore_strategy(req)


@router.post(
    "/api/strategies/{strategy_name}/init",
    tags=["Live Engine - Strategy Management"],
    summary="Initialize Strategy",
    description="Trigger compilation, binding, and state validation of the strategy instance.",
)
async def init_strategy(strategy_name: str) -> dict:
    return await StrategyService.init_strategy(strategy_name)


@router.post(
    "/api/strategies/{strategy_name}/start",
    tags=["Live Engine - Strategy Management"],
    summary="Start Strategy",
    description="Enable trading execution and order submission loop for the strategy.",
)
async def start_strategy(strategy_name: str) -> dict:
    return await StrategyService.start_strategy(strategy_name)


@router.post(
    "/api/strategies/{strategy_name}/stop",
    tags=["Live Engine - Strategy Management"],
    summary="Stop Strategy",
    description="Halt the strategy's order execution loops (leaves existing orders resting).",
)
async def stop_strategy(strategy_name: str) -> dict:
    return await StrategyService.stop_strategy(strategy_name)


@router.delete(
    "/api/strategies/{strategy_name}/remove",
    tags=["Live Engine - Strategy Management"],
    summary="Remove Strategy",
    description="Gracefully stop and deregister the strategy (cancel pending orders and exit holdings).",
)
async def remove_strategy(strategy_name: str) -> dict:
    return await StrategyService.remove_strategy(strategy_name)


@router.delete(
    "/api/strategies/{strategy_name}/delete",
    tags=["Live Engine - Strategy Management"],
    summary="Delete Strategy Configuration",
    description="Permanently purge the strategy instance metadata and configuration.",
)
async def delete_strategy(strategy_name: str) -> dict:
    return await StrategyService.delete_strategy(strategy_name)


@router.get(
    "/api/strategies/holdings",
    tags=["Live Engine - Strategy Management"],
    summary="Get Active Positions",
    description="Query runtime state for all open option and equity contract positions across active strategies.",
)
async def get_strategy_holdings() -> dict:
    return await StrategyService.get_strategy_holdings()


# --- Live Engine - Orders & Trades ---
@router.get(
    "/api/orders-trades",
    tags=["Live Engine - Orders & Trades"],
    summary="Get Orders and Trades",
    description="Retrieve live resting orders and completed trade execution receipts for the current session.",
)
async def get_orders_and_trades() -> dict:
    return await MainService.get_orders_and_trades()


@router.get(
    "/api/data/portfolios",
    tags=["Live Engine - Orders & Trades"],
    summary="Get Portfolio Names",
    description="Retrieve a list of all registered portfolio names.",
)
async def get_portfolio_names() -> dict:
    return await MainService.get_portfolio_names()


# --- Live Engine - Diagnostic Logs ---
@router.get(
    "/logs",
    tags=["Live Engine - Diagnostic Logs"],
    summary="Get Diagnostic Logs (JSON)",
    description="Read recent system and engine diagnostic logs from the memory buffer.",
)
def get_logs(limit: int = 200) -> dict:
    return MainService.get_logs(limit)


@router.get(
    "/api/logs",
    tags=["Live Engine - Diagnostic Logs"],
    summary="Get API Server Logs",
    description="Read logs specifically generated by the FastAPI gateway server.",
)
def get_logs_api() -> dict:
    return MainService.get_logs_api()


@router.post(
    "/api/logs/clear",
    tags=["Live Engine - Diagnostic Logs"],
    summary="Clear Diagnostic Logs Buffer",
    description="Clear the in-memory diagnostic logs buffer.",
)
def clear_logs() -> dict:
    return MainService.clear_logs()


# --- Live Engine - Model Registry ---
@router.post(
    "/api/models/upload",
    tags=["Live Engine - Model Registry"],
    summary="Upload Model Artifact",
    description="Upload a serialized TorchScript (.pt) model artifact directly to the models registry directory.",
)
async def upload_model(
    model_id: str = Query(..., description="Unique ID for the model registry, e.g. deep_hedge_ffnn_v2"),
    file: UploadFile = File(...),
) -> dict:
    if not file.filename.endswith(".pt"):
        raise HTTPException(status_code=400, detail="Only serialized PyTorch models (.pt extension) are supported.")
    
    # Target directory is project root / models
    workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    models_dir = os.path.join(workspace_root, "models")
    os.makedirs(models_dir, exist_ok=True)
    
    dest_path = os.path.join(models_dir, f"{model_id}.pt")
    
    # Save the file
    try:
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save model file: {e}")
        
    return {
        "status": "ok",
        "message": f"Successfully uploaded model {model_id} to {dest_path}",
        "model_id": model_id,
        "path": dest_path
    }
