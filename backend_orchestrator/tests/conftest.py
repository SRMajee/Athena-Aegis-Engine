import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
from contextlib import asynccontextmanager

# Ensure backend_orchestrator is in the python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Mock live_client_lifespan to prevent background status polling and log streaming
import src.infra.live_client_lifespan

@asynccontextmanager
async def dummy_lifespan(*args, **kwargs):
    from src.infra.state import AppState
    AppState.live.live_client = None
    AppState.live.live_status = {
        "status": "stopped",
        "connected": False,
        "detail": "live_client not initialized",
    }
    yield

src.infra.live_client_lifespan.live_client_lifespan = dummy_lifespan

@pytest.fixture(scope="session", autouse=True)
def mock_redis_and_arq():
    """Mock redis and arq connection to prevent real network calls during lifespan startup."""
    import redis.asyncio as aioredis
    import arq
    
    mock_r = MagicMock()
    mock_r.close = AsyncMock()
    
    mock_aq = MagicMock()
    mock_aq.close = AsyncMock()
    
    # Patch before any other imports
    aioredis.from_url = lambda *args, **kwargs: mock_r
    arq.create_pool = AsyncMock(return_value=mock_aq)
    
    return mock_r, mock_aq

@pytest.fixture
def client(mock_redis_and_arq):
    """FastAPI TestClient fixture."""
    from fastapi.testclient import TestClient
    from server_fastapi import app
    
    with TestClient(app) as c:
        yield c

@pytest.fixture
def mock_engine_client(client, monkeypatch):
    """Fixture to mock EngineClient and inject it into AppState, ordered after client."""
    from src.infra.state import AppState
    
    client_mock = MagicMock()
    client_mock.connect_gateway = AsyncMock(return_value={"status": "ok", "message": "connected"})
    client_mock.disconnect_gateway = AsyncMock(return_value={"status": "ok", "message": "disconnected"})
    client_mock.start_market_data = AsyncMock(return_value={"status": "ok", "message": "market data started"})
    client_mock.stop_market_data = AsyncMock(return_value={"status": "ok", "message": "market data stopped"})
    client_mock.get_status = AsyncMock(return_value={"status": "ok", "detail": "engine: running; ib: on; md: on"})
    
    # Strategy mocks
    client_mock.list_strategies = AsyncMock(return_value=[])
    client_mock.get_strategy_holdings = AsyncMock(return_value={})
    client_mock.get_orders_and_trades = AsyncMock(return_value={"orders": [], "trades": []})
    
    # Make sure we cover both list_strategy_classes and get_strategy_classes
    client_mock.list_strategy_classes = AsyncMock(return_value=["StraddleTestStrategy", "IronCondorTestStrategy"])
    client_mock.get_strategy_classes = AsyncMock(return_value=["StraddleTestStrategy", "IronCondorTestStrategy"])
    
    client_mock.get_strategy_class_defaults = AsyncMock(return_value={"param1": 10.0})
    client_mock.get_portfolio_names = AsyncMock(return_value=["DefaultPortfolio"])
    client_mock.get_portfolios_meta = AsyncMock(return_value=["DefaultPortfolio"])
    client_mock.get_removed_strategies = AsyncMock(return_value=["OldStrategy"])
    
    client_mock.add_strategy = AsyncMock(return_value={"status": "ok", "name": "NewStrat"})
    client_mock.init_strategy = AsyncMock(return_value={"status": "ok"})
    client_mock.start_strategy = AsyncMock(return_value={"status": "ok"})
    client_mock.stop_strategy = AsyncMock(return_value={"status": "ok"})
    client_mock.remove_strategy = AsyncMock(return_value={"status": "ok"})
    client_mock.delete_strategy = AsyncMock(return_value={"status": "ok"})
    
    # Set app state
    AppState.live.live_client = client_mock
    AppState.live.live_status = {
        "status": "running",
        "connected": True,
        "detail": "engine: running; ib: on; md: on"
    }
    yield client_mock
    
    AppState.live.live_client = None
    AppState.live.live_status = {
        "status": "stopped",
        "connected": False,
        "detail": "live_client not initialized"
    }

@pytest.fixture
def mock_db_session(monkeypatch):
    """Fixture to mock DB async_session_maker sessions."""
    import src.infra.db as db
    
    session = AsyncMock()
    session.add = MagicMock()
    # Mock context manager behavior
    session_maker = MagicMock()
    session_maker.return_value.__aenter__ = AsyncMock(return_value=session)
    session_maker.return_value.__aexit__ = AsyncMock()
    
    monkeypatch.setattr(db, "async_session_maker", session_maker)
    
    # Patch direct imports in other modules to avoid local references resolving to original object
    for module_name in ["src.services.backtest", "src.api.backtest", "src.infra.websockets", "src.infra.task_queue"]:
        try:
            import importlib
            mod = importlib.import_module(module_name)
            if hasattr(mod, "async_session_maker"):
                monkeypatch.setattr(mod, "async_session_maker", session_maker)
        except ImportError:
            pass
            
    yield session
