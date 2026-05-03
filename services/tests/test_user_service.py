from fastapi.testclient import TestClient


def test_user_service_health(service_loader):
    module = service_loader("user-service")
    client = TestClient(module.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_user_service_get_user_ok(service_loader):
    module = service_loader("user-service")
    client = TestClient(module.app)
    response = client.get("/users/1")
    assert response.status_code == 200
    assert response.json() == {"id": 1, "name": "Ana"}


def test_user_service_get_user_not_found(service_loader):
    module = service_loader("user-service")
    client = TestClient(module.app)
    response = client.get("/users/999")
    assert response.status_code == 404
