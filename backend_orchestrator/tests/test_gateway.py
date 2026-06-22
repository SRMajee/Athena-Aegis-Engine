import pytest

def test_connect_gateway_success(client, mock_engine_client):
    """Test gateway connection success when client is running."""
    response = client.post("/api/gateway/connect")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "connected"}
    mock_engine_client.connect_gateway.assert_called_once()

def test_connect_gateway_not_loaded(client):
    """Test connect gateway returning 400 when gRPC client is not started/loaded."""
    from src.infra.state import AppState
    print("DEBUG_LIVE_CLIENT:", AppState.live.live_client)
    response = client.post("/api/gateway/connect")
    assert response.status_code == 400
    assert "live engine (gRPC) not started" in response.json()["detail"]

def test_disconnect_gateway(client, mock_engine_client):
    """Test gateway disconnect endpoint."""
    response = client.post("/api/gateway/disconnect")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "disconnected"}
    mock_engine_client.disconnect_gateway.assert_called_once()

def test_gateway_status_connected(client, mock_engine_client):
    """Test gateway status endpoint when connected."""
    response = client.get("/api/gateway/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert data["connected"] is True
    mock_engine_client.get_status.assert_called_once()

def test_gateway_status_disconnected(client, mock_engine_client):
    """Test gateway status endpoint when disconnected."""
    mock_engine_client.get_status.return_value = {"status": "ok", "detail": "engine: running; ib: off; md: off"}
    response = client.get("/api/gateway/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "stopped"
    assert data["connected"] is False

def test_gateway_status_no_client(client):
    """Test gateway status endpoint when gRPC client is not available."""
    response = client.get("/api/gateway/status")
    assert response.status_code == 200
    assert response.json() == {"status": "stopped", "connected": False}

def test_market_status_running(client, mock_engine_client):
    """Test market data status endpoint when running."""
    response = client.get("/api/market/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert data["connected"] is True

def test_market_status_stopped(client, mock_engine_client):
    """Test market data status endpoint when stopped."""
    mock_engine_client.get_status.return_value = {"status": "ok", "detail": "engine: running; ib: on; md: off"}
    response = client.get("/api/market/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "stopped"
    assert data["connected"] is False

def test_market_start(client, mock_engine_client):
    """Test start market data endpoint."""
    response = client.post("/api/market/start")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "market data started"}
    mock_engine_client.start_market_data.assert_called_once()

def test_market_stop(client, mock_engine_client):
    """Test stop market data endpoint."""
    response = client.post("/api/market/stop")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "market data stopped"}
    mock_engine_client.stop_market_data.assert_called_once()
