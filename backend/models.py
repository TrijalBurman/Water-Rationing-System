from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")]
Percent = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
Flow = Annotated[float, Field(ge=0, le=1000, allow_inf_nan=False)]
TankMode = Literal["NORMAL", "WARNING", "RATIONING", "CRITICAL", "SENSOR_FAULT"]
FlatStatus = Literal["NORMAL", "SUSPECTED_LEAK", "LEAK_ALERT"]


class Telemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: Identifier
    flat_id: Identifier = "101"
    timestamp: datetime
    level_percent: Percent
    volume_l: float = Field(ge=0, allow_inf_nan=False)
    flow_lpm: Flow
    flow_out_lpm: Flow
    ultrasonic_distance_cm: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    sensor_status: Literal["ok", "fault"] = "ok"
    valve_percent: Percent = 0
    hardware_profile: Literal["legacy", "two_tank_transfer"] = "legacy"
    level_sensor_model: Literal["JSN-SR04T", "AJ-SR04M"] = "JSN-SR04T"
    float_switch_role: Literal["receiver_full", "source_low"] | None = None
    float_switch_state: Literal["permit", "stop_or_disconnected", "recovering"] | None = None
    transfer_permitted: bool | None = Field(default=None, strict=True)
    local_stop_reason: (
        Literal["none", "setup_required", "float_stop", "float_recovering", "clock_unsynced"] | None
    ) = None
    # This reports the commanded relay output, not a valve-position sensor.
    relay_energized: bool | None = Field(default=None, strict=True)
    requested_valve_percent: Percent | None = None
    receiver_capacity_l: float | None = Field(default=None, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_hardware_profile(self):
        if self.hardware_profile != "two_tank_transfer":
            return self
        required = (
            "float_switch_role",
            "float_switch_state",
            "transfer_permitted",
            "local_stop_reason",
            "relay_energized",
            "requested_valve_percent",
            "receiver_capacity_l",
        )
        if self.level_sensor_model != "AJ-SR04M" or any(
            getattr(self, name) is None for name in required
        ):
            raise ValueError(
                "two_tank_transfer requires AJ-SR04M and complete local safety metadata"
            )
        if self.transfer_permitted:
            if self.local_stop_reason != "none" or self.float_switch_state != "permit":
                raise ValueError(
                    "permitted transfer requires a clear stop reason and a permitted float"
                )
        elif self.local_stop_reason == "none":
            raise ValueError("stopped transfer requires a local stop reason")
        return self

    @model_validator(mode="after")
    def normalize_sensor_status(self):
        if self.ultrasonic_distance_cm is None or not 20 <= self.ultrasonic_distance_cm <= 600:
            self.sensor_status = "fault"
        return self

    @field_validator("timestamp")
    @classmethod
    def timestamp_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value.astimezone(UTC)


class Decision(BaseModel):
    mode: Literal[
        "NORMAL",
        "WARNING",
        "RATIONING",
        "CRITICAL",
        "SENSOR_FAULT",
        "LEAK_ALERT",
        "TRANSFER_STOPPED",
    ]
    tank_mode: TankMode
    flat_status: FlatStatus
    master_valve_percent: Percent
    flat_valve_percent: Percent
    predicted_flow_lpm: Flow
    eta_minutes: float | None
    leak_detected: bool
    leak_rate_lpm: float
    leak_threshold_lpm: float
    priority: int
    reason: str


class Command(Decision):
    device_id: Identifier
    command_id: str
    issued_at: datetime
    expires_at: datetime


class DemoAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["start", "stop", "scenario", "reset"]
    scenario: (
        Literal["normal", "warning", "rationing", "critical", "leak", "sensor_fault", "recovery"]
        | None
    ) = None
