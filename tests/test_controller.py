from datetime import timedelta

import pytest

from backend.controller import Controller


def test_normal_level_is_normal(frame):
    decision = Controller(capacity_l=200).decide(frame())
    assert decision.mode == "NORMAL"
    assert decision.eta_minutes == 280
    assert decision.master_valve_percent == decision.flat_valve_percent == 100


def test_low_level_always_closes_valve(frame):
    decision = Controller(capacity_l=200).decide(frame(level_percent=9, volume_l=18))
    assert decision.mode == "CRITICAL"
    assert decision.master_valve_percent == decision.flat_valve_percent == 0


def test_short_eta_rations_flow(frame):
    decision = Controller(capacity_l=200).decide(frame(level_percent=30, volume_l=60, flow_lpm=1))
    assert decision.mode == "RATIONING"
    assert decision.eta_minutes == 40
    assert decision.master_valve_percent == 30


@pytest.mark.parametrize("distance", [0, 19.9, 600.1, None])
def test_invalid_ultrasonic_reading_is_sensor_fault(frame, distance):
    decision = Controller(capacity_l=200).decide(frame(ultrasonic_distance_cm=distance))
    assert decision.mode == "SENSOR_FAULT"
    assert decision.eta_minutes is None
    assert decision.master_valve_percent == 30


def test_transient_flow_discrepancy_is_debounced(frame):
    controller = Controller(capacity_l=200)
    for _ in range(2):
        decision = controller.decide(frame(flow_out_lpm=0))
        assert decision.flat_status == "SUSPECTED_LEAK"
        assert not decision.leak_detected
        assert decision.flat_valve_percent == 100


def test_sustained_differential_triggers_flat_leak_alert_while_tank_remains_normal(frame):
    controller = Controller(capacity_l=200)
    for _ in range(3):
        decision = controller.decide(frame(flow_out_lpm=0))
    assert decision.mode == decision.flat_status == "LEAK_ALERT"
    assert decision.tank_mode == "NORMAL"
    assert decision.master_valve_percent == 100
    assert decision.flat_valve_percent == 25


def test_critical_reserve_overrides_leak_throttle(frame):
    controller = Controller(capacity_l=200)
    for _ in range(3):
        decision = controller.decide(frame(level_percent=5, volume_l=10, flow_out_lpm=0))
    assert decision.mode == "CRITICAL"
    assert decision.leak_detected
    assert decision.master_valve_percent == decision.flat_valve_percent == 0


def test_leak_recovery_when_flow_balance_restored(frame):
    controller = Controller(capacity_l=200)
    for _ in range(3):
        controller.decide(frame(flow_out_lpm=0))
    decision = controller.decide(frame())
    assert decision.mode == decision.flat_status == "NORMAL"
    assert not decision.leak_detected
    assert decision.flat_valve_percent == 100


@pytest.mark.parametrize(
    "level,flow,mode,eta",
    [
        (40, 0.5, "NORMAL", 120),
        (40, 1, "WARNING", 60),
        (24, 0, "RATIONING", None),
        (10, 0.5, "RATIONING", 0),
        (80, 0, "NORMAL", None),
    ],
)
def test_boundaries_and_no_flow_are_explicit(frame, level, flow, mode, eta):
    decision = Controller(capacity_l=200).decide(
        frame(level_percent=level, volume_l=level * 2, flow_lpm=flow)
    )
    assert decision.mode == mode
    assert decision.eta_minutes == eta


def test_five_sample_average_drops_oldest(frame):
    controller = Controller(capacity_l=200)
    for flow in [5, 1, 1, 1, 1, 1]:
        decision = controller.decide(frame(flow_lpm=flow, flow_out_lpm=flow))
    assert decision.predicted_flow_lpm == 1


def test_devices_have_independent_leak_debounce(frame):
    controller = Controller(capacity_l=200)
    controller.decide(frame(device_id="a", flow_out_lpm=0))
    controller.decide(frame(device_id="b", flow_out_lpm=0))
    decision = controller.decide(frame(device_id="a", flow_out_lpm=0))
    assert not decision.leak_detected


def test_gap_resets_debounce_and_forecast(frame):
    controller = Controller(capacity_l=200)
    one = frame(flow_out_lpm=0)
    controller.decide(one)
    controller.decide(frame(flow_out_lpm=0))
    decision = controller.decide(
        frame(flow_out_lpm=0, timestamp=one.timestamp + timedelta(seconds=30))
    )
    assert decision.flat_status == "SUSPECTED_LEAK"


def test_duplicate_does_not_advance_debounce(frame):
    controller = Controller(capacity_l=200)
    one = frame(flow_out_lpm=0)
    controller.decide(one)
    with pytest.raises(ValueError, match="strictly newer"):
        controller.decide(one)
    assert controller.states[one.device_id].leak_cycles == 1


def test_relative_threshold_and_equality_do_not_trigger(frame):
    decision = Controller(capacity_l=200).decide(frame(flow_lpm=10, flow_out_lpm=8.5))
    assert decision.leak_threshold_lpm == 1.5
    assert decision.flat_status == "NORMAL"


def test_low_volume_and_fault_cannot_release_reserve(frame):
    decision = Controller(capacity_l=200).decide(frame(volume_l=10, ultrasonic_distance_cm=None))
    assert decision.mode == "CRITICAL"
    assert decision.master_valve_percent == 0


def test_fault_and_leak_both_caps_apply(frame):
    controller = Controller(capacity_l=200)
    for _ in range(3):
        decision = controller.decide(frame(ultrasonic_distance_cm=None, flow_out_lpm=0))
    assert decision.mode == "SENSOR_FAULT"
    assert decision.master_valve_percent == 30
    assert decision.flat_valve_percent == 25
