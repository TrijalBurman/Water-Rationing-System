from datetime import datetime, timedelta, timezone

import pytest

from app.config import Settings
from app.forecast import calculate_forecast
from app.models import SystemMode, TelemetryReading


def reading(level: float, minutes: int, flow: float = 2.0, downstream: float | None = None) -> TelemetryReading:
    return TelemetryReading(
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=minutes),
        tank_level_percent=level,
        flow_lpm=flow,
        downstream_flow_lpm=downstream,
    )


def test_forecast_enters_rationing_when_ttd_is_critical() -> None:
    settings = Settings(critical_ttd_hours=4.0, warning_ttd_hours=12.0)
    result = calculate_forecast(
        [
            reading(80, 0),
            reading(70, 30),
            reading(60, 60),
        ],
        settings,
    )

    assert result.ttd_hours == 3.0
    assert result.mode == SystemMode.RATIONING


def test_forecast_detects_flow_loss_leak() -> None:
    settings = Settings(leak_loss_threshold_percent=20.0)
    result = calculate_forecast(
        [
            reading(80, 0, flow=2.0, downstream=2.0),
            reading(79, 10, flow=2.0, downstream=1.4),
        ],
        settings,
    )

    assert result.leak_detected is True
    assert result.volume_loss_percent == pytest.approx(30.0)
    assert "ANOMALY DETECTED" in result.message
