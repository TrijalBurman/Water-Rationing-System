import asyncio
import logging
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from .config import Settings
from .controller import Controller
from .demo import DemoSimulator
from .integrations import InfluxRecorder, MqttBridge
from .models import Command, Telemetry
from .storage import Recorder

logger = logging.getLogger(__name__)


class IngestionError(ValueError):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


class WaterService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.recorder = Recorder(
            settings.data_dir / f"waterwise-{settings.app_mode}.sqlite3",
            settings.quota_timezone,
            settings.stale_after_seconds,
        )
        self.controller = Controller(settings.tank_capacity_l, settings.stale_after_seconds)
        self.mqtt = MqttBridge(settings)
        self.influx = InfluxRecorder(settings, self.recorder)
        self.demo = DemoSimulator(self)
        self.ingestion_lock = asyncio.Lock()
        self.stop_event = asyncio.Event()
        self.tasks: list[asyncio.Task] = []
        self.rejected_readings = 0

    async def start(self):
        await asyncio.to_thread(
            self.recorder.prune,
            datetime.now(UTC) - timedelta(days=self.settings.history_retention_days),
        )
        # Warm up the rolling window from persisted recent samples after a service restart.
        after = datetime.now(UTC) - timedelta(seconds=self.settings.stale_after_seconds)
        for device in self.recorder.devices():
            for snapshot in self.recorder.recent(device, after)[-5:]:
                self.controller.decide(Telemetry.model_validate(snapshot["telemetry"]))
        self.mqtt.start()
        self.tasks = [
            asyncio.create_task(self._consume_mqtt(), name="mqtt-ingestion"),
            asyncio.create_task(self.influx.run(), name="influx-outbox"),
            asyncio.create_task(self._maintenance(), name="history-retention"),
        ]
        if self.settings.demo_autostart:
            await self.demo.start()

    async def _consume_mqtt(self):
        while not self.stop_event.is_set():
            try:
                telemetry = await asyncio.wait_for(self.mqtt.queue.get(), timeout=1)
            except TimeoutError:
                continue
            try:
                await self.ingest(telemetry, source="hardware")
            except IngestionError:
                self.rejected_readings += 1
                logger.warning("Rejected stale, conflicting, or invalid hardware reading")
            except Exception:
                logger.exception("Telemetry ingestion failed; device command will expire")
            finally:
                self.mqtt.queue.task_done()

    async def _maintenance(self):
        while not self.stop_event.is_set():
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=3600)
            except TimeoutError:
                await asyncio.to_thread(
                    self.recorder.prune,
                    datetime.now(UTC) - timedelta(days=self.settings.history_retention_days),
                )

    async def ingest(self, telemetry: Telemetry, source: str = "api") -> dict:
        async with self.ingestion_lock:
            now = datetime.now(UTC)
            age = (now - telemetry.timestamp).total_seconds()
            if age > self.settings.telemetry_max_age_seconds or age < -5:
                raise IngestionError(
                    "Telemetry timestamp is stale or more than five seconds in the future"
                )
            if telemetry.volume_l > self.settings.tank_capacity_l * 1.01:
                raise IngestionError("volume_l exceeds configured TANK_CAPACITY_L")
            if (
                self.demo.running
                and source != "demo"
                and telemetry.device_id == self.settings.default_device_id
            ):
                raise IngestionError(
                    "Stop the simulator before posting telemetry for its device", 409
                )
            previous = self.recorder.latest(telemetry.device_id)
            if previous:
                if (
                    datetime.fromisoformat(previous["telemetry"]["timestamp"])
                    >= telemetry.timestamp
                ):
                    raise IngestionError("Duplicate or out-of-order telemetry", 409)
                if previous["telemetry"]["flat_id"] != telemetry.flat_id:
                    raise IngestionError(
                        "Device flat_id cannot change within a recorder history", 409
                    )
            old_state = deepcopy(self.controller.states.get(telemetry.device_id))
            try:
                decision = self.controller.decide(telemetry)
                snapshot = await asyncio.to_thread(
                    self.recorder.save, telemetry, decision, now, source
                )
            except Exception:
                if old_state is None:
                    self.controller.reset(telemetry.device_id)
                else:
                    self.controller.states[telemetry.device_id] = old_state
                raise
            if age <= self.settings.stale_after_seconds:
                self.mqtt.publish(
                    Command(
                        **decision.model_dump(),
                        device_id=telemetry.device_id,
                        command_id=str(uuid4()),
                        issued_at=now,
                        expires_at=now + timedelta(seconds=self.settings.command_ttl_seconds),
                    )
                )
            return self.decorate(snapshot, now)

    def decorate(self, snapshot: dict, now: datetime | None = None) -> dict:
        now = now or datetime.now(UTC)
        telemetry = snapshot["telemetry"]
        age = (now - datetime.fromisoformat(telemetry["timestamp"])).total_seconds()
        return {
            **snapshot,
            "stale": age > self.settings.stale_after_seconds,
            "age_seconds": round(max(0, age), 1),
            "quota": self.recorder.quota(telemetry["flat_id"], self.settings.daily_quota_l, now),
        }

    def latest(self, device_id: str) -> dict | None:
        snapshot = self.recorder.latest(device_id)
        return self.decorate(snapshot) if snapshot else None

    def services(self) -> dict:
        return {
            "mqtt_configured": bool(self.settings.mqtt_host),
            "mqtt_connected": self.mqtt.connected,
            "influx_configured": bool(self.settings.influx_url),
            "influx_connected": self.influx.connected,
        }

    def health(self) -> dict:
        services = self.services()
        ready = (not services["mqtt_configured"] or services["mqtt_connected"]) and (
            not services["influx_configured"] or services["influx_connected"]
        )
        return {
            "status": "ok" if ready else "degraded",
            "ready": ready,
            "app_mode": self.settings.app_mode,
            **services,
            "mqtt_rejected_messages": self.mqtt.rejected_messages,
            "mqtt_publish_failures": self.mqtt.publish_failures,
            "rejected_readings": self.rejected_readings,
            "influx_write_failures": self.influx.write_failures,
            "influx_pending": self.recorder.pending_count() if services["influx_configured"] else 0,
        }

    async def close(self):
        try:
            await self.demo.stop()
        finally:
            self.stop_event.set()
            self.influx.stop_event.set()
            try:
                await self.mqtt.close()
            finally:
                results = await asyncio.gather(*self.tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, Exception):
                        logger.error("Background service ended with %s", type(result).__name__)
                try:
                    self.influx.close()
                finally:
                    self.recorder.close()
