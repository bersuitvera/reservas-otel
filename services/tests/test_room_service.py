from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine


def _build_room_client(module):
    mock_engine = MagicMock(spec=Engine)
    mock_connection = MagicMock()
    mock_engine.begin.return_value.__enter__.return_value = mock_connection

    module.app.dependency_overrides[module.get_engine] = lambda: mock_engine
    client = TestClient(module.app)
    return client, mock_connection


def test_room_service_health(service_loader):
    module = service_loader("room-service")
    client = TestClient(module.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_room_service_list_rooms(service_loader):
    module = service_loader("room-service")
    client, conn = _build_room_client(module)

    rows = [{"id": 1, "name": "Sala Test", "capacity": 8, "equipment": "TV"}]
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    conn.execute.return_value = result

    response = client.get("/rooms?capacity=6")
    assert response.status_code == 200
    assert response.json()["rooms"][0]["name"] == "Sala Test"


def test_room_service_get_room_found(service_loader):
    module = service_loader("room-service")
    client, conn = _build_room_client(module)

    row = {"id": 1, "name": "Sala A", "capacity": 6, "equipment": "TV"}
    result = MagicMock()
    result.mappings.return_value.first.return_value = row
    conn.execute.return_value = result

    response = client.get("/rooms/1")
    assert response.status_code == 200
    assert response.json()["id"] == 1


def test_room_service_get_room_not_found(service_loader):
    module = service_loader("room-service")
    client, conn = _build_room_client(module)

    result = MagicMock()
    result.mappings.return_value.first.return_value = None
    conn.execute.return_value = result

    response = client.get("/rooms/99")
    assert response.status_code == 404
