import asyncio
import logging
import math
from datetime import UTC, datetime

from .models import Telemetry

logger = logging.getLogger(__name__)

SCENARIOS = [
    {
        "id": "normal",
        "label": "Balanced supply",
        "description": "Healthy tank and balanced branch meters.",
    },
    {
        "id": "warning",
        "label": "Supply warning",
        "description": "Forecast falls between 60 and 120 minutes.",
    },
    {
        "id": "rationing",
        "label": "Water rationing",
        "description": "Less than one hour to protected reserve.",
    },
    {
        "id": "critical",
        "label": "Protected reserve",
        "description": "Tank below 10%; every valve closes.",
    },
    {
        "id": "leak",
        "label": "Branch leak",
        "description": "Three consecutive imbalanced readings isolate the branch.",
    },
    {
        "id": "sensor_fault",
        "label": "Sensor fault",
        "description": "Missing JSN-SR04T echo caps flow at 30%.",
    },
    {
        "id": "recovery",
        "label": "Flow recovered",
        "description": "Balanced flow clears the branch leak alert.",
    },
]


class DemoSimulator:
    def __init__(self, service):
        self.service = service
        self.scenario = "normal"
        self.running = False
        self.task = None
        self.stop_event = asyncio.Event()
        self.counter = 0
        self.last_valve = 0
        self.last_error: str | None = None
        self.control_lock = asyncio.Lock()

    def status(self):
        return {
            "enabled": self.service.settings.app_mode == "demo",
            "running": self.running,
            "scenario": self.scenario,
            "last_error": self.last_error,
            "device_id": self.service.settings.default_device_id,
            "scenarios": SCENARIOS,
        }

    async def start(self):
        if self.running:
            return
        self.stop_event.clear()
        self.running = True
        self.last_error = None
        try:
            await self.tick()
        except Exception:
            self.running = False
            raise
        self.task = asyncio.create_task(self.run(), name="demo-simulator")

    async def stop(self):
        self.running = False
        self.stop_event.set()
        if self.task:
            try:
                await self.task
            finally:
                self.task = None

    async def run(self):
        try:
            while self.running:
                try:
                    await asyncio.wait_for(self.stop_event.wait(), timeout=1)
                except TimeoutError:
                    await self.tick()
        except Exception as exc:
            self.last_error = f"Simulation stopped ({type(exc).__name__}). Check service logs."
            logger.exception("Demo simulation stopped")
        finally:
            self.running = False

    async def tick(self):
        self.counter += 1
        parameters = {
            "normal": (82, 0.60, 0.59),
            "warning": (55, 1.00, 0.99),
            "rationing": (30, 1.20, 1.19),
            "critical": (8, 0.0, 0.0),
            "leak": (82, 0.60, 0.05),
            "sensor_fault": (55, 0.60, 0.59),
            "recovery": (82, 0.60, 0.59),
        }
        level, flow_in, flow_out = parameters[self.scenario]
        ripple = 1 + 0.025 * math.sin(self.counter / 4)
        fault = self.scenario == "sensor_fault"
        telemetry = Telemetry(
            device_id=self.service.settings.default_device_id,
            flat_id="101",
            timestamp=datetime.now(UTC),
            level_percent=level,
            volume_l=level / 100 * self.service.settings.tank_capacity_l,
            flow_lpm=round(flow_in * ripple, 4),
            flow_out_lpm=round(flow_out * ripple, 4),
            ultrasonic_distance_cm=None if fault else round(25 + 150 * (1 - level / 100), 2),
            sensor_status="fault" if fault else "ok",
            valve_percent=self.last_valve,
        )
        result = await self.service.ingest(telemetry, source="demo")
        self.last_valve = result["decision"]["master_valve_percent"]
