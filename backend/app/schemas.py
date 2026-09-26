from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Telemetry(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    flat_id: str = Field(default="flat-101", min_length=1, max_length=64)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    level_percent: float = Field(ge=0, le=100)
    volume_l: float = Field(ge=0)
    flow_lpm: float = Field(ge=0, le=1000)
    flow_out_lpm: float | None = Field(default=None, ge=0, le=1000)
    ultrasonic_distance_cm: float = Field(ge=0, le=650)
    sensor_status: Literal["ok", "fault"] = "ok"
    valve_percent: float = Field(ge=0, le=100)
    pump_on: bool = False
    rssi: int | None = None

    @field_validator("timestamp")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class Decision(BaseModel):
    device_id: str
    flat_id: str = "flat-101"
    timestamp: datetime
    mode: Literal["NORMAL", "WARNING", "RATIONING", "CRITICAL", "RECOVERY", "SENSOR_FAULT"]
    tank_mode: Literal["NORMAL", "WARNING", "RATIONING", "CRITICAL", "RECOVERY", "SENSOR_FAULT"]
    flat_status: Literal["OK", "SUSPECTED_LEAK", "LEAK_ALERT"] = "OK"
    valve_percent: float = Field(ge=0, le=100)
    master_valve_percent: float = Field(default=100.0, ge=0, le=100)
    flat_valve_percent: float = Field(default=100.0, ge=0, le=100)
    predicted_flow_lpm: float = Field(ge=0)
    eta_minutes: float | None = Field(default=None, ge=0)
    leak_detected: bool = False
    leak_rate_lpm: float = Field(default=0.0, ge=0)
    priority: Literal["low", "medium", "high", "critical"]
    reason: str


class Health(BaseModel):
    status: str
    mqtt_connected: bool
