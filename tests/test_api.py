from __future__ import annotations

from fastapi.testclient import TestClient

from netarchitect.api import app

client = TestClient(app)


def test_dashboard_loads():
    response = client.get("/")
    assert response.status_code == 200
    assert "NetArchitect" in response.text
    assert "Decision log" in response.text
    assert "campus-core1" in response.text


def test_dashboard_metro_preset():
    response = client.get("/?preset=metro")
    assert response.status_code == 200
    assert "Multi-area OSPF" in response.text


def test_dashboard_custom_override():
    response = client.get("/?preset=campus&endpoints=5000")
    assert response.status_code == 200
    assert "Three-tier" in response.text


def test_api_design_json():
    response = client.get("/api/design?preset=metro")
    assert response.status_code == 200
    payload = response.json()
    assert payload["selected"]["topology"]["tier"] == "Collapsed core"
    assert payload["selected"]["routing"]["protocol"] == "Multi-area OSPF"


def test_api_design_with_configs():
    response = client.get("/api/design?preset=campus&include_configs=true")
    assert response.status_code == 200
    payload = response.json()
    assert "campus-core1" in payload["device_configs"]


def test_api_rejects_bad_distance():
    response = client.get("/api/design?preset=campus&distance_m=0")
    assert response.status_code == 422


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
