from types import SimpleNamespace

from fastapi.testclient import TestClient


def _resp(status_code: int, body: dict | None = None, text: str = ""):
    payload = body or {}
    return SimpleNamespace(status_code=status_code, json=lambda: payload, text=text)


def test_api_gateway_health(service_loader):
    module = service_loader("api-gateway")
    client = TestClient(module.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_api_gateway_create_reservation_success(service_loader):
    module = service_loader("api-gateway")

    async def fake_get(url, **kwargs):
        if "/users/" in url:
            return _resp(200, {"id": 1, "name": "Ana"})
        return _resp(200, {"rooms": []})

    async def fake_post(url, **kwargs):
        return _resp(200, {"id": 13, "status": "CONFIRMED"})

    module.client.get = fake_get
    module.client.post = fake_post

    client = TestClient(module.app)
    response = client.post(
        "/reservations",
        json={"room_id": 1, "user_id": 1, "start": "2026-03-01T10:00:00", "end": "2026-03-01T11:00:00"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CONFIRMED"


def test_api_gateway_create_reservation_requires_user_id(service_loader):
    module = service_loader("api-gateway")
    client = TestClient(module.app)
    response = client.post("/reservations", json={"room_id": 1})
    assert response.status_code == 400


def test_api_gateway_create_reservation_user_not_found(service_loader):
    module = service_loader("api-gateway")

    async def fake_get(url, **kwargs):
        return _resp(404, {})

    module.client.get = fake_get

    client = TestClient(module.app)
    response = client.post(
        "/reservations",
        json={"room_id": 1, "user_id": 999, "start": "2026-03-01T10:00:00", "end": "2026-03-01T11:00:00"},
    )
    assert response.status_code == 400
