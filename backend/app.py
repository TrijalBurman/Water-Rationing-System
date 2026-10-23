import asyncio
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import ROOT, Settings
from .models import Decision, DemoAction, Telemetry
from .service import IngestionError, WaterService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service = WaterService(settings)
        app.state.service = service
        try:
            await service.start()
            yield
        finally:
            await service.close()

    app = FastAPI(
        title="WaterWise · Smart Water Management",
        version="1.0.0",
        lifespan=lifespan,
        description="Reserve protection, five-sample forecasting, and independent branch leak detection.",
    )

    def service(request: Request) -> WaterService:
        return request.app.state.service

    ServiceDependency = Annotated[WaterService, Depends(service)]

    def authorize(x_api_key: Annotated[str | None, Header()] = None):
        if settings.api_key and not secrets.compare_digest(
            (x_api_key or "").encode("utf-8"), settings.api_key.encode("utf-8")
        ):
            raise HTTPException(401, "A valid X-API-Key is required for this action")

    @app.middleware("http")
    async def response_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith(("/api", "/devices", "/health")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(IngestionError)
    async def ingestion_error_handler(request: Request, error: IngestionError):
        return JSONResponse(status_code=error.status_code, content={"detail": str(error)})

    @app.get("/", include_in_schema=False)
    async def index():
        return RedirectResponse("/frontend/")

    @app.get("/health")
    async def health(svc: ServiceDependency):
        return svc.health()

    @app.get("/health/ready")
    async def ready(svc: ServiceDependency):
        status = svc.health()
        return JSONResponse(status, status_code=200 if status["ready"] else 503)

    @app.post("/telemetry", response_model=Decision, dependencies=[Depends(authorize)])
    async def telemetry(payload: Telemetry, svc: ServiceDependency):
        snapshot = await svc.ingest(payload)
        return snapshot["decision"]

    @app.get("/devices/{device_id}/latest")
    async def latest(device_id: str, svc: ServiceDependency):
        result = svc.latest(device_id)
        if result is None:
            raise HTTPException(404, "No readings for this device yet")
        return result

    @app.get("/devices/{device_id}/history")
    async def history(
        device_id: str,
        svc: ServiceDependency,
        minutes: Annotated[int, Query(ge=1, le=1440)] = 60,
    ):
        if svc.recorder.latest(device_id) is None:
            raise HTTPException(404, "No readings for this device yet")
        snapshots = await asyncio.to_thread(
            svc.recorder.recent, device_id, datetime.now(UTC) - timedelta(minutes=minutes)
        )
        points = []
        for snapshot in snapshots:
            t, d = snapshot["telemetry"], snapshot["decision"]
            points.append(
                {
                    **{
                        key: t[key]
                        for key in ("timestamp", "level_percent", "flow_lpm", "flow_out_lpm")
                    },
                    **{
                        key: d[key]
                        for key in (
                            "master_valve_percent",
                            "flat_valve_percent",
                            "eta_minutes",
                            "mode",
                            "leak_rate_lpm",
                        )
                    },
                }
            )
        return {"device_id": device_id, "points": points}

    @app.get("/api/overview")
    async def overview(svc: ServiceDependency):
        return {
            "devices": [svc.latest(device) for device in svc.recorder.devices()],
            "services": svc.services(),
            "demo_mode": settings.app_mode == "demo",
            "default_device_id": settings.default_device_id,
            "daily_quota_l": settings.daily_quota_l,
            "tank_capacity_l": settings.tank_capacity_l,
            "quota_timezone": settings.quota_timezone,
        }

    @app.get("/api/demo")
    async def demo_status(svc: ServiceDependency):
        return svc.demo.status()

    @app.post("/api/demo", dependencies=[Depends(authorize)])
    async def demo_action(payload: DemoAction, svc: ServiceDependency):
        if settings.app_mode != "demo":
            raise HTTPException(403, "Simulator is disabled in live mode")
        async with svc.demo.control_lock:
            if payload.action == "scenario" and payload.scenario is None:
                raise HTTPException(422, "scenario is required for the scenario action")
            if payload.scenario:
                svc.demo.scenario = payload.scenario
            if payload.action in ("start", "scenario"):
                await svc.demo.start()
            elif payload.action == "stop":
                await svc.demo.stop()
            elif payload.action == "reset":
                await svc.demo.stop()
                async with svc.ingestion_lock:
                    svc.recorder.reset(settings.default_device_id)
                    svc.controller.reset(settings.default_device_id)
                svc.demo.scenario = "normal"
                svc.demo.counter = 0
                svc.demo.last_valve = 0
            return svc.demo.status()

    app.mount(
        "/frontend",
        StaticFiles(directory=ROOT / "frontend", html=True, check_dir=False),
        name="frontend",
    )
    return app


app = create_app()
