import pytest
from unittest.mock import AsyncMock, MagicMock
from src.infra.state import AppState

def test_api_system_status(client):
    """Test system status returns backend running and current live status."""
    AppState.live.live_status = {"status": "connected", "connected": True, "detail": "ib: on"}
    response = client.get("/api/system/status")
    assert response.status_code == 200
    assert response.json() == {
        "backend": {"status": "running"},
        "live": {"status": "connected", "connected": True, "detail": "ib: on"}
    }

def test_restart_live_success(client, mock_engine_client):
    """Test successful soft restart when live client is initialized."""
    response = client.post("/api/system/restart_live")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "ok"
    assert res_data["disconnect"] == {"status": "ok", "message": "disconnected"}
    assert res_data["connect"] == {"status": "ok", "message": "connected"}
    mock_engine_client.disconnect_gateway.assert_called_once()
    mock_engine_client.connect_gateway.assert_called_once()

def test_restart_live_no_client(client):
    """Test restart live returns error when live client is not loaded."""
    response = client.post("/api/system/restart_live")
    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert "live_client not initialized" in response.json()["error"]

def test_api_orders_trades_db_success(client, monkeypatch):
    """Test querying orders and trades from DB view endpoint."""
    mock_row = (
        "Order",
        "2026-06-22 23:00:00",
        "Straddle1",
        "ord_123",
        "AAPL",
        "BUY",
        150.0,
        10.0,
        10.0,
        "Filled"
    )
    
    # Mock services.system.fetch_orders_trades_raw
    def mock_fetch(strategy, limit, record_type):
        # returns strategies list, rows, total_count, total_volume, daily_trades, daily_volume
        return (["Straddle1"], [mock_row], 1, 10.0, 1, 10.0)
        
    monkeypatch.setattr("src.services.system.fetch_orders_trades_raw", mock_fetch)
    
    response = client.get("/api/orders-trades/db?record_type=order&limit=10")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["total_count"] == 1
    assert res_data["total_volume"] == 10.0
    assert len(res_data["records"]) == 1
    assert res_data["records"][0]["id"] == "ord_123"
    assert res_data["records"][0]["record_type"] == "Order"

def test_api_orders_trades_db_invalid_type(client):
    """Test orders-trades DB endpoint validation fails for invalid record type."""
    response = client.get("/api/orders-trades/db?record_type=InvalidType")
    assert response.status_code == 400
    assert "record_type must be Order or Trade" in response.json()["detail"]

def test_api_database_contracts(client, monkeypatch):
    """Test query summary of database contracts metadata."""
    mock_summary = {"total_options": 500, "total_equities": 5, "chains": []}
    monkeypatch.setattr(
        "src.services.system.fetch_contracts_summary",
        lambda: mock_summary
    )
    
    response = client.get("/api/database/contracts")
    assert response.status_code == 200
    assert response.json() == mock_summary
