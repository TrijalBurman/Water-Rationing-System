from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "Water Rationing System"
    environment: str = "local"

    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_telemetry_topic: str = "water/telemetry"
    mqtt_command_topic: str = "water/commands/valve"

    influx_url: str = "http://localhost:8086"
    influx_token: str = "water-rationing-token"
    influx_org: str = "water-rationing"
    influx_bucket: str = "telemetry"

    tank_height_cm: float = 40.0
    critical_ttd_hours: float = 4.0
    warning_ttd_hours: float = 12.0
    leak_loss_threshold_percent: float = 20.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
