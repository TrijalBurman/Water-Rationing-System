from datetime import datetime, timezone
from enum import StrEnum
from pydantic import BaseModel, Field


class SystemMode(StrEnum):
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    RATIONING = "rationing"


class ValveState(StrEnum):
    OPEN = "open"
    RESTRICTED = "restricted"
    CLOSED = "closed"


class TelemetryReading(BaseModel):
    device_id: str = Field(default="esp32-demo")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tank_level_percent: float = Field(ge=0, le=100)
    flow_lpm: float = Field(ge=0)
    downstream_flow_lpm: float | None = Field(default=None, ge=0)
    temperature_c: float | None = None
    humidity_percent: float | None = Field(default=None, ge=0, le=100)


class ForecastResult(BaseModel):
    ttd_hours: float | None
    mode: SystemMode
    leak_detected: bool = False
    volume_loss_percent: float = 0.0
    message: str


class ValveCommand(BaseModel):
    state: ValveState
    reason: str
    mode: SystemMode
    issued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SystemSnapshot(BaseModel):
    latest_reading: TelemetryReading | None = None
    forecast: ForecastResult
    valve: ValveCommand
