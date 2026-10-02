from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "x-request-id" in r.headers


def test_ready_degraded_when_deps_down(monkeypatch):
    async def down():
        return False

    monkeypatch.setattr("app.api.v1.health.check_database", down)
    monkeypatch.setattr("app.api.v1.health.check_redis", down)
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 503
    assert r.json()["status"] == "degraded"


def test_ready_ok_when_deps_up(monkeypatch):
    async def up():
        return True

    monkeypatch.setattr("app.api.v1.health.check_database", up)
    monkeypatch.setattr("app.api.v1.health.check_redis", up)
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 200
    assert r.json()["checks"] == {"database": "ok", "redis": "ok"}


def test_chains_registry_has_eleven_networks_none_live():
    r = client.get("/api/v1/chains")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 11
    assert {c["id"] for c in data} >= {"ethereum", "solana", "bitcoin", "sui"}
    assert all(c["status"] == "planned" for c in data)
