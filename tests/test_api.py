import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    # Using a context manager triggers FastAPI's lifespan (startup/shutdown),
    # which is what actually loads the model onto app.state.
    with TestClient(app) as c:
        yield c


def test_health_endpoint_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["uptime_seconds"] >= 0


def test_ready_endpoint_returns_ready_once_model_loaded(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["ready"] is True


def test_metrics_endpoint_exposes_prometheus_format(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "forecast_service_requests_total" in response.text


def test_forecast_endpoint_happy_path(client):
    payload = {"series": [10, 12, 13, 12, 15, 17, 16, 19, 21, 20], "horizon": 3}
    response = client.post("/v1/forecast", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert len(body["forecast"]) == 3
    assert body["model_version"] == "holt-winters-v1"


def test_forecast_endpoint_rejects_insufficient_data(client):
    payload = {"series": [1, 2], "horizon": 1}
    response = client.post("/v1/forecast", json=payload)
    assert response.status_code == 422


def test_forecast_endpoint_rejects_invalid_horizon(client):
    payload = {"series": [1, 2, 3, 4, 5], "horizon": 0}
    response = client.post("/v1/forecast", json=payload)
    assert response.status_code == 422


def test_forecast_endpoint_rejects_empty_series(client):
    payload = {"series": [], "horizon": 1}
    response = client.post("/v1/forecast", json=payload)
    assert response.status_code == 422


def test_stats_endpoint_reflects_recent_requests(client):
    client.get("/health")
    response = client.get("/stats")
    assert response.status_code == 200
    body = response.json()
    assert "recent_request_count" in body
    assert body["recent_request_count"] >= 1


def test_response_includes_request_id_header(client):
    response = client.get("/health")
    assert "X-Request-ID" in response.headers
