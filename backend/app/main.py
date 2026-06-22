import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.forecast import calculate_forecast
from app.models import (
    ForecastResult,
    SystemMode,
    SystemSnapshot,
    TelemetryReading,
    ValveCommand,
    ValveState,
)
from app.mqtt_client import MqttService
from app.storage import InfluxTelemetryWriter, TelemetryStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()
store = TelemetryStore()
influx_writer: InfluxTelemetryWriter | None = None
mqtt_service: MqttService | None = None
last_forecast = ForecastResult(
    ttd_hours=None,
    mode=SystemMode.NORMAL,
    message="Waiting for telemetry.",
)
last_command = ValveCommand(
    state=ValveState.OPEN,
    reason="System startup.",
    mode=SystemMode.NORMAL,
)


def process_reading(reading: TelemetryReading) -> ForecastResult:
    global last_command, last_forecast

    store.add(reading)
    last_forecast = calculate_forecast(store.all(), settings)
    command = command_for_forecast(last_forecast, settings)

    if command.state != last_command.state or command.mode != last_command.mode:
        last_command = command
        if mqtt_service:
            mqtt_service.publish_valve_command(command)
        if influx_writer:
            _write_command(command)

    if influx_writer:
        _write_reading(reading, last_forecast)

    return last_forecast


def command_for_forecast(forecast: ForecastResult, _settings: Settings) -> ValveCommand:
    if forecast.mode == SystemMode.RATIONING:
        return ValveCommand(
            state=ValveState.RESTRICTED,
            reason=forecast.message,
            mode=forecast.mode,
        )
    if forecast.mode == SystemMode.CRITICAL:
        return ValveCommand(
            state=ValveState.RESTRICTED,
            reason=forecast.message,
            mode=forecast.mode,
        )
    return ValveCommand(
        state=ValveState.OPEN,
        reason=forecast.message,
        mode=forecast.mode,
    )


def _write_reading(reading: TelemetryReading, forecast: ForecastResult) -> None:
    try:
        influx_writer.write_reading(reading, forecast)  # type: ignore[union-attr]
    except Exception:
        logger.exception("Failed to write telemetry to InfluxDB")


def _write_command(command: ValveCommand) -> None:
    try:
        influx_writer.write_command(command)  # type: ignore[union-attr]
    except Exception:
        logger.exception("Failed to write valve command to InfluxDB")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global influx_writer, mqtt_service

    try:
        influx_writer = InfluxTelemetryWriter(settings)
    except Exception:
        logger.exception("InfluxDB writer disabled")
        influx_writer = None

    try:
        mqtt_service = MqttService(settings, process_reading)
        mqtt_service.start()
    except Exception:
        logger.exception("MQTT service disabled")
        mqtt_service = None

    yield

    if mqtt_service:
        mqtt_service.stop()
    if influx_writer:
        influx_writer.close()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}


@app.post("/telemetry", response_model=ForecastResult)
def ingest_telemetry(reading: TelemetryReading) -> ForecastResult:
    return process_reading(reading)


@app.get("/status", response_model=SystemSnapshot)
def get_status() -> SystemSnapshot:
    return SystemSnapshot(
        latest_reading=store.latest(),
        forecast=last_forecast,
        valve=last_command,
    )


@app.post("/commands/valve", response_model=ValveCommand)
def set_valve(command: ValveCommand) -> ValveCommand:
    global last_command

    last_command = command
    if mqtt_service:
        mqtt_service.publish_valve_command(command)
    if influx_writer:
        _write_command(command)
    return command


@app.post("/demo/reset")
def reset_demo() -> dict[str, str]:
    global store, last_command, last_forecast

    store = TelemetryStore()
    last_forecast = ForecastResult(
        ttd_hours=None,
        mode=SystemMode.NORMAL,
        message="Waiting for telemetry.",
    )
    last_command = ValveCommand(
        state=ValveState.OPEN,
        reason="Demo reset.",
        mode=SystemMode.NORMAL,
    )
    return {"status": "reset"}


@app.get("/readings", response_model=list[TelemetryReading])
def get_readings(limit: int = 50) -> list[TelemetryReading]:
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be greater than zero")
    return store.all()[-limit:]
