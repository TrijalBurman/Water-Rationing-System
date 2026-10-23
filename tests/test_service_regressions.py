import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.service import WaterService


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        data_dir=tmp_path,
        mqtt_host="",
        influx_url="",
        app_mode="demo",
        demo_autostart=False,
        api_key="test-key",
    )


@pytest.mark.parametrize("committed_samples", [0, 1])
def test_failed_persistence_allows_same_frame_retry_without_advancing_leak(
    settings, frame, committed_samples
):
    async def scenario():
        service = WaterService(settings)
        try:
            with patch.object(service.mqtt, "publish") as publish:
                for _ in range(committed_samples):
                    await service.ingest(frame(flow_out_lpm=0))
                previous = service.recorder.latest("tank-01")
                publish.reset_mock()
                reading = frame(flow_out_lpm=0)
                with patch.object(service.recorder, "save", side_effect=OSError("disk full")):
                    with pytest.raises(OSError, match="disk full"):
                        await service.ingest(reading)
                assert service.recorder.latest("tank-01") == previous
                publish.assert_not_called()

                retried = await service.ingest(reading)
                assert retried["decision"]["flat_status"] == "SUSPECTED_LEAK"
                assert retried["decision"]["flat_valve_percent"] == 100
                publish.assert_called_once()
                # Exactly three committed readings must confirm a leak.
                for _ in range(2 - committed_samples):
                    final = await service.ingest(frame(flow_out_lpm=0))
                assert final["decision"]["flat_status"] == "LEAK_ALERT"
                assert final["decision"]["flat_valve_percent"] == 25
        finally:
            await service.close()

    asyncio.run(scenario())


def test_failed_demo_start_clears_running_and_can_retry(settings):
    async def scenario():
        service = WaterService(settings)
        try:
            with patch.object(service.recorder, "save", side_effect=OSError("disk full")):
                with pytest.raises(OSError, match="disk full"):
                    await service.demo.start()
            assert not service.demo.status()["running"]
            assert service.demo.task is None
            assert service.latest("tank-01") is None

            await service.demo.start()
            assert service.demo.status()["running"]
            assert service.latest("tank-01")["source"] == "demo"
            await service.demo.stop()
            assert not service.demo.status()["running"]
            assert service.demo.task is None
        finally:
            await service.close()

    asyncio.run(scenario())


def test_demo_background_failure_can_stop_and_restart(settings):
    async def scenario():
        service = WaterService(settings)
        try:
            await service.demo.start()
            with patch.object(service.recorder, "save", side_effect=OSError("disk full")):
                await asyncio.wait_for(asyncio.shield(service.demo.task), timeout=3)
            assert not service.demo.status()["running"]
            assert "OSError" in service.demo.status()["last_error"]
            await service.demo.stop()
            assert service.demo.task is None

            await service.demo.start()
            assert service.demo.status()["running"]
            assert service.demo.status()["last_error"] is None
        finally:
            await service.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("unavailable", ["mqtt", "influx"])
def test_readiness_is_degraded_when_a_configured_dependency_is_unavailable(settings, unavailable):
    configured = settings.model_copy(
        update={
            "mqtt_host": "broker.invalid",
            "mqtt_username": "backend",
            "mqtt_password": "unused-test-password",
            "influx_url": "http://influx.invalid:8086",
            "influx_token": "unused-test-token",
        }
    )
    # Stub connection establishment so this test never opens a network connection.
    with (
        patch("backend.integrations.MqttBridge.start"),
        patch("backend.integrations.InfluxDBClient"),
        patch("backend.integrations.InfluxRecorder.run", new_callable=AsyncMock),
        TestClient(create_app(configured)) as client,
    ):
        service = client.app.state.service
        service.mqtt.connected = unavailable != "mqtt"
        service.influx.connected = unavailable != "influx"
        heartbeat = client.get("/health")
        readiness = client.get("/health/ready")
        assert heartbeat.status_code == 200
        assert heartbeat.json()["status"] == "degraded"
        assert readiness.status_code == 503
        assert readiness.json()["ready"] is False
        assert readiness.json()[f"{unavailable}_configured"] is True
        assert readiness.json()[f"{unavailable}_connected"] is False

        service.mqtt.connected = service.influx.connected = True
        assert client.get("/health/ready").status_code == 200


def test_archived_stale_reading_is_saved_without_reissuing_a_command(settings, frame):
    async def scenario():
        service = WaterService(settings)
        try:
            old = frame(timestamp=datetime.now(UTC) - timedelta(seconds=15))
            with patch.object(service.mqtt, "publish") as publish:
                archived = await service.ingest(old)
                assert archived["stale"]
                assert service.recorder.latest("tank-01")["telemetry"] == old.model_dump(
                    mode="json"
                )
                publish.assert_not_called()

                fresh = await service.ingest(frame(timestamp=datetime.now(UTC)))
                assert not fresh["stale"]
                publish.assert_called_once()
        finally:
            await service.close()

    asyncio.run(scenario())


def test_failed_worker_does_not_prevent_resource_cleanup(settings):
    async def scenario():
        service = WaterService(settings)

        async def failed_worker():
            raise OSError("maintenance failed")

        service.tasks = [asyncio.create_task(failed_worker())]
        with (
            patch.object(service.influx, "close", wraps=service.influx.close) as influx_close,
            patch.object(service.recorder, "close", wraps=service.recorder.close) as recorder_close,
        ):
            await service.close()
            influx_close.assert_called_once()
            recorder_close.assert_called_once()
        assert service.tasks[0].done()

    asyncio.run(scenario())
