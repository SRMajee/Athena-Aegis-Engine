import pytest
from unittest.mock import AsyncMock, MagicMock
from src.infra.state import AppState

def test_api_files(client, monkeypatch):
    """Test listing backtest data files."""
    mock_file = MagicMock()
    mock_file.name = "AAPL_20260601.parquet"
    mock_file.size = 12345
    mock_file.__dict__ = {"name": mock_file.name, "size": mock_file.size}
    
    monkeypatch.setattr("src.api.backtest.list_files", lambda: [mock_file])
    
    response = client.get("/api/files")
    assert response.status_code == 200
    assert response.json() == [{"name": "AAPL_20260601.parquet", "size": 12345}]

def test_api_backtest_strategies(client, monkeypatch):
    """Test fetching strategy classes list."""
    monkeypatch.setattr("src.api.backtest.list_strategies", lambda: '{"strategies": ["StraddleTestStrategy"]}')
    response = client.get("/api/backtest/strategies")
    assert response.status_code == 200
    assert response.json() == {"strategies": ["StraddleTestStrategy"]}

def test_api_file_info(client, monkeypatch):
    """Test getting single file metadata."""
    monkeypatch.setattr(
        "src.api.backtest.inspect_parquet_to_dict",
        lambda path: {"path": path, "rows": 100}
    )
    response = client.get("/api/file_info?path=data/AAPL/2026/20260601.parquet")
    assert response.status_code == 200
    assert response.json() == {"path": "data/AAPL/2026/20260601.parquet", "rows": 100}

def test_api_backtest_duration(client, monkeypatch):
    """Test getting symbols covered date range metadata."""
    monkeypatch.setattr(
        "src.api.backtest.backtest_duration",
        lambda: {"AAPL": {"start": "2026-06-01", "end": "2026-06-05"}}
    )
    response = client.get("/api/backtest_duration")
    assert response.status_code == 200
    assert response.json() == {"AAPL": {"start": "2026-06-01", "end": "2026-06-05"}}

def test_run_backtest_success(client, mock_db_session, monkeypatch):
    """Test submitting a backtest job succeeds and enqueues to ARQ."""
    # Setup AppState Redis
    mock_arq = AsyncMock()
    AppState.arq_redis = mock_arq
    
    # Mock DB returns
    mock_db_session.flush = AsyncMock()
    mock_db_session.commit = AsyncMock()
    mock_db_session.execute = AsyncMock()
    
    payload = {
        "parquet": "AAPL",
        "strategy": "StraddleTestStrategy",
        "fee_rate": 0.35,
        "slippage_bps": 5.0,
        "risk_free_rate": 0.05,
        "iv_price_mode": "mid",
        "strategy_setting": {},
        "start_date": "2026-06-01",
        "end_date": "2026-06-05"
    }
    
    response = client.post("/api/run_backtest", json=payload)
    res_data = response.json()
    print("DEBUG_RES_DATA:", res_data)
    assert response.status_code == 202
    assert res_data["status"] == "ok"
    assert "job_id" in res_data
    
    mock_arq.enqueue_job.assert_called_once()
    assert AppState.backtest.active_job_id == res_data["job_id"]

def test_run_backtest_validation_error(client):
    """Test submitting a backtest job fails validation with invalid params."""
    payload = {
        "parquet": "AAPL",
        "strategy": "StraddleTestStrategy",
        "fee_rate": -1.0,  # invalid negative fee
        "start_date": "2026-06-01",
        "end_date": "2026-06-05"
    }
    response = client.post("/api/run_backtest", json=payload)
    assert response.status_code == 202
    assert response.json()["status"] == "error"
    assert "fee_rate must be >= 0" in response.json()["error"]

def test_cancel_backtest_no_active(client):
    """Test cancel endpoint when no backtest is active."""
    AppState.backtest.active_job_id = None
    response = client.post("/api/backtest/cancel")
    assert response.status_code == 200
    assert "No active backtest job found" in response.json()["message"]

def test_cancel_backtest_active(client):
    """Test cancel endpoint with active job ID set, triggers Redis set."""
    AppState.backtest.active_job_id = "test-job-123"
    mock_redis = AsyncMock()
    AppState.redis = mock_redis
    
    response = client.post("/api/backtest/cancel")
    assert response.status_code == 200
    assert "Cancel signal sent for job test-job-123" in response.json()["message"]
    mock_redis.set.assert_called_once_with("job_cancel:test-job-123", "1", ex=60)
