import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from .controller import RationingController
from .influx_store import InfluxStore
from .mqtt_bridge import MqttBridge
from .schemas import Decision, Health, Telemetry
from .settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
settings = get_settings()
controller = RationingController(settings)
store = InfluxStore(settings)
latest: dict[str, tuple[Telemetry, Decision]] = {}


def process(telemetry: Telemetry) -> Decision:
    decision = controller.decide(telemetry)
    latest[telemetry.device_id] = (telemetry, decision)
    store.write(telemetry, decision)
    return decision


bridge = MqttBridge(settings, process)


@asynccontextmanager
async def lifespan(app: FastAPI):
    bridge.start()
    yield
    bridge.stop()
    store.close()


app = FastAPI(title="Smart Water Rationing API", version="1.0.0", lifespan=lifespan)


@app.get("/health", response_model=Health)
def health() -> Health:
    return Health(status="ok", mqtt_connected=bridge.connected)


@app.post("/telemetry", response_model=Decision)
def ingest(telemetry: Telemetry) -> Decision:
    decision = process(telemetry)
    if bridge.connected:
        bridge.publish_command(decision)
    return decision


@app.get("/devices/{device_id}/latest")
def latest_status(device_id: str) -> dict:
    if device_id not in latest:
        raise HTTPException(status_code=404, detail="No telemetry for this device")
    telemetry, decision = latest[device_id]
    return {"telemetry": telemetry, "decision": decision}

