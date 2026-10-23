import asyncio
import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.config import Settings
from backend.controller import Controller
from backend.integrations import InfluxRecorder, MqttBridge
from backend.models import Command
from backend.storage import Recorder


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        tank_capacity_l=200,  # Historical controller fixtures explicitly exercise a 200L tank.
        data_dir=tmp_path,
        mqtt_host="",
        influx_url="",
        app_mode="demo",
        demo_autostart=False,
        api_key="test-key",
    )


def make_command(reading):
    now = datetime.now(UTC)
    return Command(
        **Controller(capacity_l=200).decide(reading).model_dump(),
        device_id=reading.device_id,
        command_id="test-command",
        issued_at=now,
        expires_at=now + timedelta(seconds=10),
    )


def snapshot(reading):
    return {
        "telemetry": reading.model_dump(mode="json"),
        "decision": Controller(capacity_l=200).decide(reading).model_dump(mode="json"),
        "source": "hardware",
    }


@pytest.mark.parametrize("mode", ["demo", "live"])
def test_only_live_mqtt_bridge_subscribes_and_publishes_commands(settings, frame, mode):
    bridge = MqttBridge(settings.model_copy(update={"app_mode": mode}))
    bridge.client = Mock()
    bridge.client.publish.return_value.rc = 0
    bridge._on_connect(bridge.client, None, None, SimpleNamespace(is_failure=False), None)
    command = make_command(frame())
    bridge.publish(command)
    assert bridge.connected
    if mode == "demo":
        bridge.client.subscribe.assert_not_called()
        bridge.client.publish.assert_not_called()
    else:
        bridge.client.subscribe.assert_called_once_with("watertank/+/telemetry", qos=1)
        bridge.client.publish.assert_called_once()
        args, kwargs = bridge.client.publish.call_args
        assert args[0] == "watertank/tank-01/command"
        assert Command.model_validate_json(args[1]) == command
        assert kwargs == {"qos": 1, "retain": False}


def test_disconnected_bridge_does_not_queue_commands(settings, frame):
    bridge = MqttBridge(settings.model_copy(update={"app_mode": "live"}))
    bridge.client = Mock()
    bridge.publish(make_command(frame()))
    bridge.client.publish.assert_not_called()


@pytest.mark.parametrize(
    "invalid",
    ["retained", "wrong_device", "wrong_topic", "bad_json", "oversized"],
)
def test_mqtt_rejects_unsafe_messages_before_enqueueing(settings, frame, invalid):
    bridge = MqttBridge(settings)
    bridge.loop = Mock()
    message = SimpleNamespace(
        topic="watertank/tank-01/telemetry",
        payload=frame().model_dump_json().encode(),
        retain=False,
    )
    if invalid == "retained":
        message.retain = True
    elif invalid == "wrong_device":
        message.topic = "watertank/tank-02/telemetry"
    elif invalid == "wrong_topic":
        message.topic = "watertank/tank-01/command"
    elif invalid == "bad_json":
        message.payload = b"invalid json"
    elif invalid == "oversized":
        message.payload = b" " * 8193
    bridge._on_message(None, None, message)
    assert bridge.rejected_messages == 1
    assert bridge.queue.empty()
    bridge.loop.call_soon_threadsafe.assert_not_called()


def test_valid_mqtt_message_reaches_the_async_ingestion_queue(settings, frame):
    async def scenario():
        bridge = MqttBridge(settings.model_copy(update={"app_mode": "live"}))
        bridge.loop = asyncio.get_running_loop()
        reading = frame()
        bridge._on_message(
            None,
            None,
            SimpleNamespace(
                topic="watertank/tank-01/telemetry",
                payload=reading.model_dump_json().encode(),
                retain=False,
            ),
        )
        received = await asyncio.wait_for(bridge.queue.get(), timeout=1)
        assert received == reading
        assert bridge.rejected_messages == 0

    asyncio.run(scenario())


def test_influx_omits_unavailable_eta_and_distance_but_keeps_sensor_fault(frame):
    reading = frame(ultrasonic_distance_cm=None, sensor_status="fault")
    line = InfluxRecorder.point(snapshot(reading)).to_line_protocol()
    assert "eta_minutes=" not in line
    assert "ultrasonic_distance_cm=" not in line
    assert 'sensor_status="fault"' in line
    assert 'tank_mode="SENSOR_FAULT"' in line
    assert "leak_detected=false" in line


@pytest.mark.parametrize("level,volume,expected_valve", [(80, 160, 100), (5, 10, 0)])
def test_influx_point_uses_stable_numeric_types_and_device_timestamp(
    frame, level, volume, expected_valve
):
    reading = frame(level_percent=level, volume_l=volume)
    line = InfluxRecorder.point(snapshot(reading)).to_line_protocol()
    tags, remaining = line.split(" ", 1)
    fields, timestamp = remaining.rsplit(" ", 1)
    assert tags == "water_telemetry,device_id=tank-01,flat_id=101,source=hardware"
    value = re.search(r"(?:^|,)master_valve_percent=([^,]+)", fields).group(1)
    assert not value.endswith("i")  # Influx integer suffix would conflict with later floats.
    assert float(value) == expected_valve
    expected_ns = int(reading.timestamp.timestamp()) * 1_000_000_000
    expected_ns += reading.timestamp.microsecond * 1000
    assert int(timestamp) == expected_ns


def test_influx_failed_write_keeps_outbox_for_identical_retry(settings, tmp_path, frame):
    recorder = Recorder(tmp_path / "outbox.sqlite3", "UTC", 6)
    influx = InfluxRecorder(settings, recorder)
    influx.writer = Mock()
    influx.client = Mock()
    try:
        reading = frame()
        recorder.save(
            reading, Controller(capacity_l=200).decide(reading), datetime.now(UTC), "hardware"
        )
        influx.writer.write.side_effect = [OSError("temporarily unavailable"), None]
        with pytest.raises(OSError, match="temporarily unavailable"):
            influx._flush()
        assert recorder.pending_count() == 1
        assert not influx.connected

        influx._flush()
        assert recorder.pending_count() == 0
        assert influx.connected
        attempts = influx.writer.write.call_args_list
        assert attempts[0].kwargs["bucket"] == settings.influx_bucket
        assert attempts[0].kwargs["record"][0].to_line_protocol() == (
            attempts[1].kwargs["record"][0].to_line_protocol()
        )
    finally:
        influx.close()
        recorder.close()


def test_outbox_ack_after_reset_does_not_skip_new_telemetry(settings, tmp_path, frame):
    recorder = Recorder(tmp_path / "outbox.sqlite3", "UTC", 6)
    influx = InfluxRecorder(settings, recorder)
    influx.writer = Mock()
    influx.client = Mock()
    try:
        first = frame()
        recorder.save(first, Controller(capacity_l=200).decide(first), datetime.now(UTC), "demo")
        old_id = recorder.pending()[0][0]
        replacement = frame()

        def reset_during_write(**kwargs):
            recorder.reset("tank-01")
            recorder.save(
                replacement,
                Controller(capacity_l=200).decide(replacement),
                datetime.now(UTC),
                "demo",
            )

        influx.writer.write.side_effect = reset_during_write
        influx._flush()
        pending = recorder.pending()
        assert len(pending) == 1
        assert pending[0][0] != old_id
        assert pending[0][1]["telemetry"] == replacement.model_dump(mode="json")
    finally:
        influx.close()
        recorder.close()
