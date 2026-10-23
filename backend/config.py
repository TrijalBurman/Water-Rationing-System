from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    app_mode: Literal["demo", "live"] = "demo"
    demo_autostart: bool = False
    api_key: str = ""
    data_dir: Path = ROOT / "data"
    tank_capacity_l: float = Field(default=2.5, gt=0)
    daily_quota_l: float = Field(default=150, gt=0)
    quota_timezone: str = "Asia/Kolkata"
    default_device_id: str = "tank-01"
    stale_after_seconds: int = Field(default=6, ge=2)
    telemetry_max_age_seconds: int = Field(default=30, ge=5)
    history_retention_days: int = Field(default=7, ge=1, le=365)
    command_ttl_seconds: int = Field(default=10, ge=2, le=30)
    mqtt_host: str = ""
    mqtt_port: int = Field(default=1883, ge=1, le=65535)
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_tls: bool = False
    mqtt_ca_file: str | None = None
    influx_url: str = ""
    influx_token: str = ""
    influx_org: str = "waterwise"
    influx_bucket: str = "water_telemetry"

    @model_validator(mode="after")
    def require_credentials(self):
        if self.mqtt_host and not (self.mqtt_username and self.mqtt_password):
            raise ValueError("MQTT_USERNAME and MQTT_PASSWORD are required when MQTT_HOST is set")
        if self.influx_url and not self.influx_token:
            raise ValueError("INFLUX_TOKEN is required when INFLUX_URL is set")
        if self.app_mode == "live" and not self.api_key:
            raise ValueError("Set API_KEY for live operation")
        if self.app_mode == "live" and self.demo_autostart:
            raise ValueError("DEMO_AUTOSTART is only allowed in demo mode")
        # Validate now, rather than on the first midnight usage calculation.
        from zoneinfo import ZoneInfo

        ZoneInfo(self.quota_timezone)
        return self
