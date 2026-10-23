from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        data_dir=tmp_path,
        app_mode="demo",
        api_key="test-key",
        mqtt_host="",
        influx_url="",
        demo_autostart=False,
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def send(client, telemetry):
    return client.post(
        "/telemetry", json=telemetry.model_dump(mode="json"), headers={"X-API-Key": "test-key"}
    )


def test_telemetry_latest_history_and_quota(client, frame):
    for _ in range(3):
        assert send(client, frame(flow_out_lpm=0.5)).status_code == 200
    latest = client.get("/devices/tank-01/latest").json()
    assert latest["decision"]["tank_mode"] == "NORMAL"
    assert latest["quota"]["consumed_l"] == pytest.approx(0.017, abs=0.001)
    assert not latest["stale"]
    assert len(client.get("/devices/tank-01/history").json()["points"]) == 3
    assert len(client.get("/api/overview").json()["devices"]) == 1
    assert client.get("/health").json()["status"] == "ok"


def test_duplicate_is_conflict_and_does_not_confirm_leak(client, frame):
    one = frame(flow_out_lpm=0)
    assert send(client, one).status_code == 200
    for _ in range(3):
        assert send(client, one).status_code == 409
    assert (
        client.get("/devices/tank-01/latest").json()["decision"]["flat_status"] == "SUSPECTED_LEAK"
    )


def test_write_auth_and_public_reads(client, frame):
    assert client.post("/telemetry", json=frame().model_dump(mode="json")).status_code == 401
    assert client.post("/api/demo", json={"action": "start"}).status_code == 401
    assert client.get("/api/overview").status_code == 200


def test_non_ascii_api_key_returns_unauthorized(client):
    response = client.post("/api/demo", json={"action": "start"}, headers={b"X-API-Key": b"\xff"})
    assert response.status_code == 401


@pytest.mark.parametrize(
    "updates",
    [
        {"level_percent": -1},
        {"flow_lpm": -0.1},
        {"ultrasonic_distance_cm": -1},
        {"level_percent": 101},
        {"timestamp": "2026-01-01T00:00:00"},
        {"device_id": "a/+/telemetry"},
        {"sensor_status": "maybe"},
        {"unknown": "value"},
    ],
)
def test_schema_rejects_invalid_input(client, frame, updates):
    data = frame().model_dump(mode="json") | updates
    response = client.post("/telemetry", json=data, headers={"X-API-Key": "test-key"})
    assert response.status_code == 422


@pytest.mark.parametrize("offset", [-60, 60])
def test_stale_and_future_readings_rejected(client, frame, offset):
    response = send(client, frame(timestamp=datetime.now(UTC) + timedelta(seconds=offset)))
    assert response.status_code == 422
    assert client.get("/devices/tank-01/latest").status_code == 404


def test_excess_volume_rejected(client, frame):
    assert send(client, frame(volume_l=300)).status_code == 422


def test_history_range_validation_and_missing_device(client):
    assert client.get("/devices/missing/latest").status_code == 404
    assert client.get("/devices/missing/history").status_code == 404
    assert client.get("/devices/missing/history?minutes=0").status_code == 422


def test_simulator_lifecycle_and_conflict(client, frame):
    headers = {"X-API-Key": "test-key"}
    assert client.get("/api/demo").json()["running"] is False
    response = client.post(
        "/api/demo", json={"action": "start", "scenario": "critical"}, headers=headers
    )
    assert response.json()["running"] is True
    assert client.get("/devices/tank-01/latest").json()["decision"]["mode"] == "CRITICAL"
    assert send(client, frame(timestamp=datetime.now(UTC))).status_code == 409
    assert (
        client.post("/api/demo", json={"action": "stop"}, headers=headers).json()["running"]
        is False
    )
    assert client.post("/api/demo", json={"action": "scenario"}, headers=headers).status_code == 422
    assert client.post("/api/demo", json={"action": "reset"}, headers=headers).status_code == 200
    assert client.get("/devices/tank-01/latest").status_code == 404


def test_simulator_disabled_in_live_mode(settings):
    settings.app_mode = "live"
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/demo", json={"action": "start"}, headers={"X-API-Key": "test-key"}
        )
        assert response.status_code == 403


def test_local_history_survives_restart(settings, frame):
    with TestClient(create_app(settings)) as first:
        assert send(first, frame()).status_code == 200
    with TestClient(create_app(settings)) as second:
        assert second.get("/devices/tank-01/latest").json()["telemetry"]["volume_l"] == 160
