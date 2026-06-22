from collections.abc import Sequence
from statistics import mean

from app.config import Settings
from app.models import ForecastResult, SystemMode, TelemetryReading


def calculate_forecast(
    readings: Sequence[TelemetryReading], settings: Settings
) -> ForecastResult:
    if not readings:
        return ForecastResult(
            ttd_hours=None,
            mode=SystemMode.NORMAL,
            message="Waiting for telemetry.",
        )

    latest = readings[-1]
    ttd_hours = _estimate_ttd_hours(readings)
    leak_loss = _calculate_volume_loss_percent(latest)
    leak_detected = leak_loss >= settings.leak_loss_threshold_percent

    if ttd_hours is not None and ttd_hours <= settings.critical_ttd_hours:
        mode = SystemMode.RATIONING
        message = "CRITICAL ALERT: Shortage predicted. Autonomous rationing engaged."
    elif ttd_hours is not None and ttd_hours <= settings.warning_ttd_hours:
        mode = SystemMode.WARNING
        message = "WARNING: Water shortage risk increasing."
    else:
        mode = SystemMode.NORMAL
        message = "System healthy."

    if leak_detected:
        mode = SystemMode.CRITICAL if mode == SystemMode.NORMAL else mode
        message = (
            f"ANOMALY DETECTED: {leak_loss:.1f}% volume loss. "
            "Potential leak between sensor zones."
        )

    return ForecastResult(
        ttd_hours=ttd_hours,
        mode=mode,
        leak_detected=leak_detected,
        volume_loss_percent=leak_loss,
        message=message,
    )


def _estimate_ttd_hours(readings: Sequence[TelemetryReading]) -> float | None:
    latest = readings[-1]
    if len(readings) < 2:
        return None

    recent = list(readings)[-12:]
    slopes_per_hour: list[float] = []

    for previous, current in zip(recent, recent[1:]):
        elapsed_hours = (
            current.timestamp - previous.timestamp
        ).total_seconds() / 3600
        if elapsed_hours <= 0:
            continue

        level_change = previous.tank_level_percent - current.tank_level_percent
        if level_change > 0:
            slopes_per_hour.append(level_change / elapsed_hours)

    if slopes_per_hour:
        drain_rate_percent_per_hour = mean(slopes_per_hour)
    else:
        # Fallback for demo data where level is temporarily stable.
        drain_rate_percent_per_hour = latest.flow_lpm * 0.25

    if drain_rate_percent_per_hour <= 0:
        return None

    return latest.tank_level_percent / drain_rate_percent_per_hour


def _calculate_volume_loss_percent(reading: TelemetryReading) -> float:
    if reading.downstream_flow_lpm is None or reading.flow_lpm <= 0:
        return 0.0

    loss = reading.flow_lpm - reading.downstream_flow_lpm
    if loss <= 0:
        return 0.0

    return (loss / reading.flow_lpm) * 100
