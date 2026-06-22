from collections import deque
from collections.abc import Iterable

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from app.config import Settings
from app.models import ForecastResult, TelemetryReading, ValveCommand


class TelemetryStore:
    def __init__(self, max_readings: int = 240) -> None:
        self._readings: deque[TelemetryReading] = deque(maxlen=max_readings)

    def add(self, reading: TelemetryReading) -> None:
        self._readings.append(reading)

    def latest(self) -> TelemetryReading | None:
        return self._readings[-1] if self._readings else None

    def all(self) -> list[TelemetryReading]:
        return list(self._readings)


class InfluxTelemetryWriter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = InfluxDBClient(
            url=settings.influx_url,
            token=settings.influx_token,
            org=settings.influx_org,
        )
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)

    def write_reading(self, reading: TelemetryReading, forecast: ForecastResult) -> None:
        point = (
            Point("water_telemetry")
            .tag("device_id", reading.device_id)
            .field("tank_level_percent", reading.tank_level_percent)
            .field("flow_lpm", reading.flow_lpm)
            .field("downstream_flow_lpm", reading.downstream_flow_lpm or 0.0)
            .field("temperature_c", reading.temperature_c or 0.0)
            .field("humidity_percent", reading.humidity_percent or 0.0)
            .field("ttd_hours", forecast.ttd_hours or -1.0)
            .field("volume_loss_percent", forecast.volume_loss_percent)
            .field("leak_detected", forecast.leak_detected)
            .tag("mode", forecast.mode.value)
            .time(reading.timestamp)
        )
        self.write_api.write(
            bucket=self.settings.influx_bucket,
            org=self.settings.influx_org,
            record=point,
        )

    def write_command(self, command: ValveCommand) -> None:
        point = (
            Point("valve_commands")
            .tag("state", command.state.value)
            .tag("mode", command.mode.value)
            .field("reason", command.reason)
            .time(command.issued_at)
        )
        self.write_api.write(
            bucket=self.settings.influx_bucket,
            org=self.settings.influx_org,
            record=point,
        )

    def close(self) -> None:
        self.client.close()


def seed_store(store: TelemetryStore, readings: Iterable[TelemetryReading]) -> None:
    for reading in readings:
        store.add(reading)
