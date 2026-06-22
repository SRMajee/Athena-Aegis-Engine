import pytest
from src.infra.state import AppState

def test_api_logs(client):
    """Test fetching recent logs (endpoint /api/logs)."""
    AppState.live.log_buffer = ["Log entry 1", "Log entry 2"]
    response = client.get("/api/logs")
    assert response.status_code == 200
    assert response.json() == {"logs": ["Log entry 1", "Log entry 2"]}

def test_logs_endpoint_with_limit(client):
    """Test fetching logs with custom limit (endpoint /logs)."""
    AppState.live.log_buffer = ["Log 1", "Log 2", "Log 3"]
    response = client.get("/logs?limit=2")
    assert response.status_code == 200
    assert response.json() == {"logs": ["Log 2", "Log 3"]}

def test_clear_logs(client):
    """Test clearing the log buffer."""
    AppState.live.log_buffer = ["Log 1", "Log 2"]
    response = client.post("/api/logs/clear")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(AppState.live.log_buffer) == 0
