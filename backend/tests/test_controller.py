from app.controller import RationingController
from app.schemas import Telemetry
from app.settings import Settings


def telemetry(**changes):
    values = {
        "device_id": "tank-01", "level_percent": 70, "volume_l": 140,
        "flow_lpm": 1.0, "ultrasonic_distance_cm": 35, "valve_percent": 100,
    }
    values.update(changes)
    return Telemetry(**values)


def controller():
    return RationingController(Settings(tank_capacity_l=200, min_safe_percent=10))


def test_normal_level_is_normal():
    result = controller().decide(telemetry())
    assert result.tank_mode == "NORMAL"
    assert result.mode == "NORMAL"
    assert result.flat_status == "OK"
    assert result.master_valve_percent == 100
    assert result.flat_valve_percent == 100
    assert result.valve_percent == 100


def test_low_level_always_closes_valve():
    result = controller().decide(telemetry(level_percent=8, volume_l=16))
    assert result.tank_mode == "CRITICAL"
    assert result.mode == "CRITICAL"
    assert result.master_valve_percent == 0
    assert result.flat_valve_percent == 0
    assert result.valve_percent == 0


def test_short_eta_rations_flow():
    result = controller().decide(telemetry(level_percent=35, volume_l=70, flow_lpm=2))
    assert result.tank_mode == "RATIONING"
    assert result.flat_status == "OK"
    assert 20 <= result.flat_valve_percent <= 70
    assert result.master_valve_percent == result.flat_valve_percent


def test_invalid_ultrasonic_reading_is_sensor_fault():
    result = controller().decide(telemetry(ultrasonic_distance_cm=10.0))
    assert result.tank_mode == "SENSOR_FAULT"
    assert result.flat_valve_percent <= 30


def test_balanced_dual_flow_remains_normal():
    c = controller()
    t = telemetry(flow_lpm=0.8, flow_out_lpm=0.78)
    result = c.decide(t)
    assert result.tank_mode == "NORMAL"
    assert result.flat_status == "OK"
    assert result.valve_percent == 100
    assert result.leak_detected is False
    assert result.leak_rate_lpm == 0.0


def test_transient_flow_discrepancy_is_debounced():
    c = controller()
    # 1st sample with discrepancy: not confirmed yet (requires 3 samples)
    # With usable_l=120 and flow_lpm=0.8, ETA=150min > 120min warning threshold -> tank_mode remains NORMAL
    r1 = c.decide(telemetry(flow_lpm=0.8, flow_out_lpm=0.2))
    assert r1.tank_mode == "NORMAL"
    assert r1.flat_status == "SUSPECTED_LEAK"
    assert r1.leak_detected is False

    # 2nd sample: still not confirmed
    r2 = c.decide(telemetry(flow_lpm=0.8, flow_out_lpm=0.2))
    assert r2.tank_mode == "NORMAL"
    assert r2.flat_status == "SUSPECTED_LEAK"
    assert r2.leak_detected is False


def test_sustained_differential_triggers_flat_leak_alert_while_tank_remains_normal():
    c = controller()
    # 3 consecutive samples with substantial inflow > outflow (delta = 0.6 L/m > 0.3 L/m threshold)
    c.decide(telemetry(flow_lpm=0.8, flow_out_lpm=0.2))
    c.decide(telemetry(flow_lpm=0.8, flow_out_lpm=0.2))
    r3 = c.decide(telemetry(flow_lpm=0.8, flow_out_lpm=0.2))

    # Central tank remains NORMAL because volume (70%) and ETA (150m) are healthy
    assert r3.tank_mode == "NORMAL"
    assert r3.master_valve_percent == 100.0

    # Flat 101 branch is isolated in LEAK_ALERT and throttled to 25%
    assert r3.flat_status == "LEAK_ALERT"
    assert r3.leak_detected is True
    assert r3.flat_valve_percent == 25.0
    assert r3.valve_percent == 25.0
    assert r3.leak_rate_lpm == 0.6
    assert r3.priority == "high"


def test_critical_reserve_overrides_leak_throttle():
    c = controller()
    # 3 consecutive samples trigger leak
    for _ in range(3):
        c.decide(telemetry(level_percent=70, volume_l=140, flow_lpm=2.0, flow_out_lpm=0.5))

    # Central tank drops below protected 10% reserve -> all valves must close to 0%
    crit = c.decide(telemetry(level_percent=8, volume_l=16, flow_lpm=2.0, flow_out_lpm=0.5))
    assert crit.tank_mode == "CRITICAL"
    assert crit.flat_status == "LEAK_ALERT"
    assert crit.master_valve_percent == 0.0
    assert crit.flat_valve_percent == 0.0
    assert crit.valve_percent == 0.0


def test_leak_recovery_when_flow_balance_restored():
    c = controller()
    # Trigger leak alert
    for _ in range(3):
        c.decide(telemetry(flow_lpm=2.0, flow_out_lpm=0.5))

    # Next reading: pipeline repaired, outflow matches inflow with ETA >= 120 min
    rec = c.decide(telemetry(volume_l=230, flow_lpm=0.5, flow_out_lpm=0.5))
    assert rec.flat_status == "OK"
    assert rec.leak_detected is False
    assert rec.flat_valve_percent == 100
    assert rec.master_valve_percent == 100
