"""Two-tank metadata, local stop priority, and durable integration behavior."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app import create_app
from backend.config import Settings
from backend.controller import Controller
from backend.integrations import InfluxRecorder, MqttBridge
from backend.models import Telemetry

PROFILE = {
    "hardware_profile": "two_tank_transfer",
    "level_sensor_model": "AJ-SR04M",
    "float_switch_role": "receiver_full",
    "float_switch_state": "permit",
    "transfer_permitted": True,
    "local_stop_reason": "none",
    "relay_energized": False,
    "requested_valve_percent": 100,
    "receiver_capacity_l": 1.5,
}


def profile_frame(frame, **updates):
    return frame(**(PROFILE | updates))


@pytest.mark.parametrize("field", [name for name in PROFILE if name != "hardware_profile"])
@pytest.mark.parametrize("missing", [True, False], ids=["missing", "null"])
def test_two_tank_profile_requires_complete_metadata(frame, field, missing):
    payload = profile_frame(frame).model_dump(mode="json")
    if missing:
        payload.pop(field)
    else:
        payload[field] = None
    with pytest.raises(ValidationError):
        Telemetry.model_validate(payload)


@pytest.mark.parametrize(
    "updates",
    [
        {"level_sensor_model": "JSN-SR04T"},
        {"float_switch_role": "receiver_low"},
        {"float_switch_state": "full"},
        {"local_stop_reason": "unknown"},
        {"transfer_permitted": "false"},
        {"relay_energized": 1},
        {"requested_valve_percent": 101},
        {"receiver_capacity_l": 0},
        {"receiver_capacity_l": float("inf")},
        {"transfer_permitted": True, "local_stop_reason": "setup_required"},
        {"transfer_permitted": True, "float_switch_state": "recovering"},
        {"transfer_permitted": False, "local_stop_reason": "none"},
    ],
)
def test_two_tank_profile_rejects_ambiguous_states(frame, updates):
    with pytest.raises(ValidationError):
        profile_frame(frame, **updates)


@pytest.mark.parametrize(
    "reason,state,expected",
    [
        ("setup_required", "permit", "source tank geometry is uncalibrated"),
        ("float_stop", "stop_or_disconnected", "full or the float circuit is disconnected"),
        ("float_recovering", "recovering", "waiting for a stable permitted state"),
        ("clock_unsynced", "permit", "clock is not synchronized"),
    ],
)
def test_local_stop_overrides_otherwise_fully_open_commands(frame, reason, state, expected):
    reading = profile_frame(
        frame,
        transfer_permitted=False,
        local_stop_reason=reason,
        float_switch_state=state,
        valve_percent=100,
    )
    decision = Controller(capacity_l=200).decide(reading)
    assert decision.mode == "TRANSFER_STOPPED"
    assert decision.tank_mode == ("SENSOR_FAULT" if reason == "setup_required" else "NORMAL")
    assert decision.priority == 95
    assert decision.master_valve_percent == decision.flat_valve_percent == 0
    assert expected in decision.reason


def test_source_low_float_reason_does_not_claim_receiver_is_full(frame):
    decision = Controller(capacity_l=200).decide(
        profile_frame(
            frame,
            transfer_permitted=False,
            local_stop_reason="float_stop",
            float_switch_role="source_low",
            float_switch_state="stop_or_disconnected",
        )
    )
    assert "Source low-level float" in decision.reason
    assert "Receiver" not in decision.reason


def test_source_reserve_has_priority_over_transfer_stop_and_leak(frame):
    controller = Controller(capacity_l=200)
    for _ in range(3):
        decision = controller.decide(
            profile_frame(
                frame,
                level_percent=5,
                volume_l=10,
                flow_out_lpm=0,
                transfer_permitted=False,
                local_stop_reason="float_stop",
                float_switch_state="stop_or_disconnected",
            )
        )
    assert decision.mode == decision.tank_mode == "CRITICAL"
    assert decision.priority == 100
    assert decision.leak_detected
    assert decision.master_valve_percent == decision.flat_valve_percent == 0
    assert "Protected source reserve" in decision.reason
    assert "full or the float circuit is disconnected" in decision.reason


@pytest.mark.parametrize(
    "updates,tank_mode,source_limit,pipe_limit",
    [
        ({}, "NORMAL", 100, 25),
        ({"ultrasonic_distance_cm": None}, "SENSOR_FAULT", 30, 25),
        ({"level_percent": 20, "volume_l": 40}, "RATIONING", 20, 20),
    ],
)
def test_permitted_transfer_preserves_source_and_leak_limits(
    frame, updates, tank_mode, source_limit, pipe_limit
):
    controller = Controller(capacity_l=200)
    for _ in range(3):
        decision = controller.decide(profile_frame(frame, flow_out_lpm=0, **updates))
    assert decision.tank_mode == tank_mode
    assert decision.flat_status == "LEAK_ALERT"
    assert decision.master_valve_percent == source_limit
    assert decision.flat_valve_percent == pipe_limit
    assert min(decision.master_valve_percent, decision.flat_valve_percent) == pipe_limit


def test_local_gate_is_independent_of_network_command_and_relay_output(frame):
    reading = profile_frame(frame, requested_valve_percent=0, valve_percent=0)
    assert reading.transfer_permitted
    assert not reading.relay_energized
    decision = Controller(capacity_l=200).decide(reading)
    assert decision.mode == "NORMAL"
    assert decision.master_valve_percent == decision.flat_valve_percent == 100


def test_inconsistent_energized_output_is_accepted_and_stop_command_is_issued(frame):
    reading = profile_frame(
        frame,
        transfer_permitted=False,
        local_stop_reason="float_stop",
        float_switch_state="stop_or_disconnected",
        relay_energized=True,
        requested_valve_percent=0,
    )
    decision = Controller(capacity_l=200).decide(reading)
    assert decision.mode == "TRANSFER_STOPPED"
    assert decision.master_valve_percent == decision.flat_valve_percent == 0


def test_legacy_telemetry_remains_compatible_without_hardware_claims(frame):
    reading = frame()
    assert reading.hardware_profile == "legacy"
    assert reading.level_sensor_model == "JSN-SR04T"
    assert reading.float_switch_role is None
    assert reading.transfer_permitted is None
    assert reading.relay_energized is None
    decision = Controller(capacity_l=200).decide(reading)
    assert decision.mode == "NORMAL"
    assert decision.master_valve_percent == decision.flat_valve_percent == 100


def test_two_tank_metadata_survives_api_history_and_restart(tmp_path, frame):
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        app_mode="live",
        api_key="test-key",
        tank_capacity_l=2.5,
        mqtt_host="",
        influx_url="",
        demo_autostart=False,
    )
    reading = profile_frame(
        frame,
        timestamp=datetime.now(UTC),
        level_percent=0,
        volume_l=0,
        sensor_status="fault",
        transfer_permitted=False,
        local_stop_reason="setup_required",
        requested_valve_percent=0,
        valve_percent=0,
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/telemetry",
            json=reading.model_dump(mode="json"),
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        latest = client.get("/devices/tank-01/latest").json()
        assert latest["telemetry"] == reading.model_dump(mode="json")
        assert latest["decision"]["mode"] == "TRANSFER_STOPPED"
        assert latest["decision"]["tank_mode"] == "SENSOR_FAULT"
        history = client.get("/devices/tank-01/history").json()["points"]
        assert history[0]["mode"] == "TRANSFER_STOPPED"
        assert history[0]["local_stop_reason"] == "setup_required"
        assert history[0]["hardware_profile"] == "two_tank_transfer"
        assert history[0]["receiver_capacity_l"] == 1.5
        overview_response = client.get("/api/overview").json()
        assert overview_response["tank_capacity_l"] == 2.5
        overview = overview_response["devices"][0]
        assert overview["telemetry"]["local_stop_reason"] == "setup_required"
        assert overview["telemetry"]["relay_energized"] is False
        persisted = client.app.state.service.recorder.latest("tank-01")
        assert persisted["telemetry"]["receiver_capacity_l"] == 1.5
    with TestClient(create_app(settings)) as restarted:
        latest = restarted.get("/devices/tank-01/latest").json()
        assert latest["telemetry"]["hardware_profile"] == "two_tank_transfer"
        assert latest["telemetry"]["transfer_permitted"] is False
        assert latest["decision"]["master_valve_percent"] == 0


@pytest.mark.parametrize("permitted", [True, False])
def test_influx_uses_explicit_boolean_string_and_float_metadata_types(frame, permitted):
    reading = profile_frame(
        frame,
        transfer_permitted=permitted,
        local_stop_reason="none" if permitted else "float_stop",
        float_switch_state="permit" if permitted else "stop_or_disconnected",
        relay_energized=permitted,
        requested_valve_percent=100 if permitted else 0,
    )
    snapshot = {
        "telemetry": reading.model_dump(mode="json"),
        "decision": Controller(capacity_l=200).decide(reading).model_dump(mode="json"),
        "source": "hardware",
    }
    line = InfluxRecorder.point(snapshot).to_line_protocol()
    assert 'hardware_profile="two_tank_transfer"' in line
    assert 'level_sensor_model="AJ-SR04M"' in line
    assert "receiver_capacity_l=1.5" in line
    assert 'float_switch_role="receiver_full"' in line
    assert f"transfer_permitted={str(permitted).lower()}" in line
    assert f"relay_energized={str(permitted).lower()}" in line
    assert f'local_stop_reason="{reading.local_stop_reason}"' in line
    assert f'float_switch_state="{reading.float_switch_state}"' in line
    assert f"requested_valve_percent={100 if permitted else 0}" in line
    assert "requested_valve_percent=100i" not in line
    assert "requested_valve_percent=0i" not in line


def test_influx_accepts_persisted_snapshot_that_predates_new_fields(frame):
    reading = frame()
    telemetry = reading.model_dump(mode="json")
    for field in PROFILE:
        telemetry.pop(field)
    point = InfluxRecorder.point(
        {
            "telemetry": telemetry,
            "decision": Controller(capacity_l=200).decide(reading).model_dump(mode="json"),
            "source": "hardware",
        }
    ).to_line_protocol()
    assert 'sensor_status="ok"' in point
    assert "hardware_profile=" not in point
    assert "transfer_permitted=" not in point


def test_mqtt_ingestion_accepts_two_tank_metadata_and_rejects_incomplete_profile(tmp_path, frame):
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        app_mode="live",
        api_key="test-key",
        mqtt_host="",
        influx_url="",
        demo_autostart=False,
    )
    bridge = MqttBridge(settings)
    bridge.loop = Mock()
    reading = profile_frame(frame)
    message = SimpleNamespace(
        topic="watertank/tank-01/telemetry",
        payload=reading.model_dump_json().encode(),
        retain=False,
    )
    bridge._on_message(None, None, message)
    assert bridge.loop.call_soon_threadsafe.call_args.args[1] == reading
    bridge.loop.reset_mock()
    message.payload = (
        frame(hardware_profile="legacy")
        .model_dump_json()
        .replace('"hardware_profile":"legacy"', '"hardware_profile":"two_tank_transfer"')
        .encode()
    )
    bridge._on_message(None, None, message)
    assert bridge.rejected_messages == 1
    bridge.loop.call_soon_threadsafe.assert_not_called()


def test_uncalibrated_zero_is_stopped_without_claiming_source_is_empty(frame):
    reading = profile_frame(
        frame,
        level_percent=0,
        volume_l=0,
        sensor_status="fault",
        transfer_permitted=False,
        local_stop_reason="setup_required",
        requested_valve_percent=0,
        valve_percent=0,
    )
    decision = Controller(capacity_l=2.5).decide(reading)
    assert decision.mode == "TRANSFER_STOPPED"
    assert decision.tank_mode == "SENSOR_FAULT"
    assert decision.eta_minutes is None
    assert decision.master_valve_percent == decision.flat_valve_percent == 0
    assert "uncalibrated" in decision.reason
    assert "reserve reached" not in decision.reason.lower()


def test_actual_tanks_use_quarter_litre_source_reserve(frame):
    assert Settings(_env_file=None).tank_capacity_l == 2.5
    reading = profile_frame(
        frame,
        level_percent=9.96,
        volume_l=0.249,
        receiver_capacity_l=1.5,
        flow_lpm=0.5,
        flow_out_lpm=0.5,
    )
    decision = Controller().decide(reading)
    assert decision.mode == "CRITICAL"
    assert decision.master_valve_percent == decision.flat_valve_percent == 0
    assert reading.receiver_capacity_l == 1.5
    at_reserve = Controller(capacity_l=2.5).decide(
        profile_frame(
            frame,
            level_percent=10,
            volume_l=0.25,
            flow_lpm=0.5,
            flow_out_lpm=0.5,
        )
    )
    assert at_reserve.tank_mode == "RATIONING"
    assert at_reserve.eta_minutes == 0
