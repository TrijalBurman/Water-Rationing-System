import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from .controller import RationingController
from .influx_store import InfluxStore
from .mqtt_bridge import MqttBridge
from .schemas import Decision, Health, Telemetry
from .settings import get_settings

STATIC_DIR = Path(__file__).parent / "static"

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
@app.get("/", response_class=FileResponse)
def portal_root():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse("<h1>Smart Water Rationing API</h1><p>API is running. See <a href='/docs'>/docs</a>.</p>")


@app.get("/portal", response_class=FileResponse)
def portal_page():
    return portal_root()


@app.get("/devices/{device_id}/latest")
def latest_status(device_id: str) -> dict:
    if device_id not in latest:
        raise HTTPException(status_code=404, detail="No telemetry for this device")
    telemetry, decision = latest[device_id]
    return {"telemetry": telemetry, "decision": decision}

