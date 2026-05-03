from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine


def _build_reservation_context(module):
    mock_engine = MagicMock(spec=Engine)
    mock_conn = MagicMock()
    mock_engine.begin.return_value.__enter__.return_value = mock_conn
    module.engine = mock_engine
    module.redis = MagicMock()
    return mock_conn


def test_reservation_service_health(service_loader):
    module = service_loader("reservation-service")
    client = TestClient(module.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_reservation_service_ensure_room_exists_ok(service_loader):
    module = service_loader("reservation-service")
    module.http_client = SimpleNamespace(get=lambda url: SimpleNamespace(status_code=200))
    module.ensure_room_exists(1)


def test_reservation_service_ensure_room_exists_404(service_loader):
    module = service_loader("reservation-service")
    module.http_client = SimpleNamespace(get=lambda url: SimpleNamespace(status_code=404))
    try:
        module.ensure_room_exists(1)
    except Exception as exc:  # HTTPException
        assert getattr(exc, "status_code", None) == 400
    else:
        assert False, "Expected HTTPException"


def test_reservation_service_create_conflict(service_loader):
    module = service_loader("reservation-service")
    conn = _build_reservation_context(module)
    module.ensure_room_exists = lambda room_id: None

    # Primera query (COUNT) devuelve solape > 0.
    overlap_result = MagicMock()
    overlap_result.scalar_one.return_value = 1
    conn.execute.return_value = overlap_result

    client = TestClient(module.app)
    response = client.post(
        "/reservations",
        json={"room_id": 1, "user_id": 1, "start": "2026-03-01T10:00:00", "end": "2026-03-01T11:00:00"},
    )
    assert response.status_code == 409


def test_reservation_service_create_success(service_loader):
    module = service_loader("reservation-service")
    conn = _build_reservation_context(module)
    module.ensure_room_exists = lambda room_id: None

    overlap_result = MagicMock()
    overlap_result.scalar_one.return_value = 0
    insert_result = MagicMock()
    insert_result.scalar_one.return_value = 13
    conn.execute.side_effect = [overlap_result, insert_result]

    client = TestClient(module.app)
    response = client.post(
        "/reservations",
        json={"room_id": 1, "user_id": 1, "start": "2026-03-01T10:00:00", "end": "2026-03-01T11:00:00"},
    )
    assert response.status_code == 200
    assert response.json() == {"id": 13, "status": "CONFIRMED"}
    assert module.redis.xadd.called
