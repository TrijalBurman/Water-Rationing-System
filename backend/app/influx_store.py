import logging

from influxdb_client import InfluxDBClient, Point, WritePrecision

from .schemas import Decision, Telemetry
from .settings import Settings

logger = logging.getLogger(__name__)


MODE_CODES = {
    "NORMAL": 0,
    "WARNING": 1,
    "RATIONING": 2,
    "CRITICAL": 3,
    "RECOVERY": 4,
    "SENSOR_FAULT": 5,
}

FLAT_STATUS_CODES = {
    "OK": 0,
    "SUSPECTED_LEAK": 1,
    "LEAK_ALERT": 2,
}


class InfluxStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: InfluxDBClient | None = None
        if settings.influxdb_token:
            self.client = InfluxDBClient(url=settings.influxdb_url, token=settings.influxdb_token, org=settings.influxdb_org, timeout=3_000)

    def write(self, telemetry: Telemetry, decision: Decision) -> None:
        if not self.client:
            return
        fields = {
            "level_percent": telemetry.level_percent,
            "volume_l": telemetry.volume_l,
            "flow_lpm": telemetry.flow_lpm,
            "ultrasonic_distance_cm": telemetry.ultrasonic_distance_cm,
            "reported_valve_percent": telemetry.valve_percent,
            "commanded_valve_percent": decision.valve_percent,
            "master_valve_percent": decision.master_valve_percent,
            "flat_valve_percent": decision.flat_valve_percent,
            "predicted_flow_lpm": decision.predicted_flow_lpm,
            "leak_rate_lpm": decision.leak_rate_lpm,
            "mode_code": MODE_CODES.get(decision.tank_mode, 0),
            "flat_status_code": FLAT_STATUS_CODES.get(decision.flat_status, 0),
        }
        if telemetry.flow_out_lpm is not None:
            fields["flow_out_lpm"] = telemetry.flow_out_lpm
        if decision.eta_minutes is not None:
            fields["eta_minutes"] = decision.eta_minutes
        point = (
            Point("water_telemetry")
            .tag("device_id", telemetry.device_id)
            .tag("flat_id", telemetry.flat_id)
            .tag("mode", decision.tank_mode)
            .tag("tank_mode", decision.tank_mode)
            .tag("flat_status", decision.flat_status)
            .tag("sensor_status", telemetry.sensor_status)
            .tag("leak_detected", str(decision.leak_detected).lower())
        )
        for name, value in fields.items():
            point.field(name, value)
        point.field("leak_detected", decision.leak_detected)
        point.field("pump_on", telemetry.pump_on)
        point.field("mode_text", decision.tank_mode)
        point.field("flat_status_text", decision.flat_status)
        point.time(telemetry.timestamp, WritePrecision.NS)
        try:
            self.client.write_api().write(bucket=self.settings.influxdb_bucket, record=point)
        except Exception:
            logger.exception("InfluxDB write failed; the control loop continues")

    def close(self) -> None:
        if self.client:
            self.client.close()
