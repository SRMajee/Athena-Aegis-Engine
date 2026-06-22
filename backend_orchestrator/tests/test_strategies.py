import pytest

def test_list_strategies(client, mock_engine_client):
    """Test listing active strategies."""
    mock_engine_client.list_strategies.return_value = [{"name": "Straddle1", "status": "running"}]
    response = client.get("/api/strategies")
    assert response.status_code == 200
    assert response.json() == {"strategies": [{"name": "Straddle1", "status": "running"}]}
    mock_engine_client.list_strategies.assert_called_once()

def test_get_strategy_updates(client):
    """Test listing strategy telemetry updates."""
    from src.infra.state import AppState
    AppState.live.strategy_updates = [{"strategy": "S1", "pnl": 120.0}]
    response = client.get("/api/strategies/updates")
    assert response.status_code == 200
    assert response.json() == {"updates": [{"strategy": "S1", "pnl": 120.0}]}

def test_clear_strategy_updates(client):
    """Test clearing strategy updates buffer."""
    from src.infra.state import AppState
    AppState.live.strategy_updates = [{"strategy": "S1", "pnl": 120.0}]
    response = client.get("/api/strategies/updates/clear")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "Strategy updates cleared"}
    assert len(AppState.live.strategy_updates) == 0

def test_get_strategy_classes(client, mock_engine_client):
    """Test strategy class listing endpoint."""
    response = client.get("/api/strategies/meta/strategy-classes")
    assert response.status_code == 200
    assert response.json() == {"classes": ["StraddleTestStrategy", "IronCondorTestStrategy"]}
    mock_engine_client.get_strategy_classes.assert_called_once()

def test_get_strategy_settings(client, mock_engine_client):
    """Test fetching default settings config for a strategy class."""
    response = client.get("/api/strategies/meta/settings?class=StraddleTestStrategy")
    assert response.status_code == 200
    assert response.json() == {"settings": {"param1": 10.0}}
    mock_engine_client.get_strategy_class_defaults.assert_called_once_with("StraddleTestStrategy")

def test_get_portfolios(client, mock_engine_client):
    """Test portfolio listing endpoint."""
    response = client.get("/api/strategies/meta/portfolios")
    assert response.status_code == 200
    assert response.json() == {"portfolios": ["DefaultPortfolio"]}
    mock_engine_client.get_portfolios_meta.assert_called_once()

def test_get_removed_strategies(client, mock_engine_client):
    """Test fetching soft-removed strategy list."""
    response = client.get("/api/strategies/meta/removed-strategies")
    assert response.status_code == 200
    assert response.json() == {"removed_strategies": ["OldStrategy"]}
    mock_engine_client.get_removed_strategies.assert_called_once()

def test_create_strategy_success(client, mock_engine_client):
    """Test strategy creation endpoint."""
    payload = {
        "strategy_class": "StraddleTestStrategy",
        "portfolio_name": "DefaultPortfolio",
        "setting": {"param1": 15.0}
    }
    response = client.post("/api/strategies", json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "name": "NewStrat"}
    mock_engine_client.add_strategy.assert_called_once_with(
        "StraddleTestStrategy", "DefaultPortfolio", {"param1": 15.0}
    )

def test_restore_strategy_unsupported(client):
    """Test restore strategy endpoint returns 400 in C++ mode."""
    payload = {
        "strategy_name": "OldStrat",
        "portfolio_name": "DefaultPortfolio",
        "setting": {}
    }
    response = client.post("/api/strategies/restore", json=payload)
    assert response.status_code == 400
    assert "RestoreStrategy is not supported in C++" in response.json()["detail"]

def test_init_strategy(client, mock_engine_client):
    """Test strategy initialization endpoint."""
    response = client.post("/api/strategies/S1/init")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_engine_client.init_strategy.assert_called_once_with("S1")

def test_start_strategy(client, mock_engine_client):
    """Test strategy start execution endpoint."""
    response = client.post("/api/strategies/S1/start")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_engine_client.start_strategy.assert_called_once_with("S1")

def test_stop_strategy(client, mock_engine_client):
    """Test strategy stop execution endpoint."""
    response = client.post("/api/strategies/S1/stop")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_engine_client.stop_strategy.assert_called_once_with("S1")

def test_remove_strategy(client, mock_engine_client):
    """Test soft-delete strategy endpoint."""
    response = client.delete("/api/strategies/S1/remove")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_engine_client.remove_strategy.assert_called_once_with("S1")

def test_delete_strategy(client, mock_engine_client):
    """Test hard-delete strategy endpoint."""
    response = client.delete("/api/strategies/S1/delete")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_engine_client.delete_strategy.assert_called_once_with("S1")
