import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

# Mockear instrumentación que no es relevante para la lógica del test.
# Se hace antes de importar la app para evitar que se ejecuten.
patch("common.apm.setup_apm").start()

from main import app, get_engine

# --- Configuración de Mocks para Inyección de Dependencias ---

mock_engine = MagicMock(spec=Engine)
mock_connection = MagicMock()
mock_engine.begin.return_value.__enter__.return_value = mock_connection

def override_get_engine():
    """Override para inyectar un motor de BD mockeado."""
    return mock_engine

# Aplicar el override a la app de FastAPI
app.dependency_overrides[get_engine] = override_get_engine

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}

def test_list_rooms_no_filter():
    mock_rows = [
        {"id": 1, "name": "Sala Test", "capacity": 10, "equipment": "TV"}
    ]
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = mock_rows
    mock_connection.execute.return_value = mock_result

    response = client.get("/rooms")

    assert response.status_code == 200
    data = response.json()
    assert "rooms" in data
    assert len(data["rooms"]) == 1
    assert data["rooms"][0]["name"] == "Sala Test"
    mock_connection.execute.assert_called_once()
    mock_connection.reset_mock()
