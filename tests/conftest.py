from datetime import UTC, datetime, timedelta

import pytest

from backend.models import Telemetry


@pytest.fixture
def frame():
    start = datetime.now(UTC) - timedelta(seconds=5)
    counter = 0

    def make(**overrides):
        nonlocal counter
        counter += 1
        data = {
            "device_id": "tank-01",
            "flat_id": "101",
            "timestamp": start + timedelta(seconds=counter),
            "level_percent": 80,
            "volume_l": 160,
            "flow_lpm": 0.5,
            "flow_out_lpm": 0.5,
            "ultrasonic_distance_cm": 55,
            "sensor_status": "ok",
            "valve_percent": 100,
        }
        data.update(overrides)
        return Telemetry(**data)

    return make
