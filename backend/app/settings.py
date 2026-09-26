from functools import lru_cache
import os

from pydantic import BaseModel, Field


class Settings(BaseModel):
    mqtt_host: str = Field(default_factory=lambda: os.getenv("MQTT_HOST", "localhost"))
    mqtt_port: int = Field(default_factory=lambda: int(os.getenv("MQTT_PORT", "1883")))
    mqtt_username: str | None = Field(default_factory=lambda: os.getenv("MQTT_USERNAME"))
    mqtt_password: str | None = Field(default_factory=lambda: os.getenv("MQTT_PASSWORD"))
    influxdb_url: str = Field(default_factory=lambda: os.getenv("INFLUXDB_URL", "http://localhost:8086"))
    influxdb_token: str | None = Field(default_factory=lambda: os.getenv("INFLUXDB_TOKEN"))
    influxdb_org: str = Field(default_factory=lambda: os.getenv("INFLUXDB_ORG", "water-system"))
    influxdb_bucket: str = Field(default_factory=lambda: os.getenv("INFLUXDB_BUCKET", "telemetry"))
    tank_capacity_l: float = Field(default_factory=lambda: float(os.getenv("TANK_CAPACITY_L", "200")))
    min_safe_percent: float = Field(default_factory=lambda: float(os.getenv("MIN_SAFE_PERCENT", "10")))
    warning_eta_minutes: float = Field(default_factory=lambda: float(os.getenv("WARNING_ETA_MINUTES", "120")))
    rationing_eta_minutes: float = Field(default_factory=lambda: float(os.getenv("RATIONING_ETA_MINUTES", "60")))
    minimum_rationing_percent: float = Field(default_factory=lambda: float(os.getenv("MIN_RATIONING_PERCENT", "20")))
    leak_diff_threshold_lpm: float = Field(default_factory=lambda: float(os.getenv("LEAK_DIFF_THRESHOLD_LPM", "0.3")))
    leak_ratio_threshold: float = Field(default_factory=lambda: float(os.getenv("LEAK_RATIO_THRESHOLD", "0.15")))
    leak_confirm_samples: int = Field(default_factory=lambda: int(os.getenv("LEAK_CONFIRM_SAMPLES", "3")))
    leak_throttle_percent: float = Field(default_factory=lambda: float(os.getenv("LEAK_THROTTLE_PERCENT", "25")))


@lru_cache
def get_settings() -> Settings:
    return Settings()

