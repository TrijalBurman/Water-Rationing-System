import asyncio
import logging
import ssl
from datetime import datetime

import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from pydantic import ValidationError

from .config import Settings
from .models import Command, Telemetry
from .storage import Recorder

logger = logging.getLogger(__name__)


class MqttBridge:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.connected = False
        self.rejected_messages = 0
        self.publish_failures = 0
        self.queue: asyncio.Queue[Telemetry] = asyncio.Queue(maxsize=500)
        self.client: mqtt.Client | None = None
        self.loop: asyncio.AbstractEventLoop | None = None

    def start(self):
        if not self.settings.mqtt_host:
            return
        self.loop = asyncio.get_running_loop()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="waterwise-backend")
        self.client.username_pw_set(self.settings.mqtt_username, self.settings.mqtt_password)
        if self.settings.mqtt_tls:
            self.client.tls_set(
                ca_certs=self.settings.mqtt_ca_file, tls_version=ssl.PROTOCOL_TLS_CLIENT
            )
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.max_queued_messages_set(100)
        self.client.connect_async(self.settings.mqtt_host, self.settings.mqtt_port, keepalive=20)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        self.connected = not reason_code.is_failure
        if self.connected and self.settings.app_mode == "live":
            client.subscribe("watertank/+/telemetry", qos=1)
        logger.info("MQTT connection %s", "ready" if self.connected else "rejected")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected = False

    def _on_message(self, client, userdata, message):
        try:
            if message.retain or len(message.payload) > 8192:
                raise ValueError("Retained or oversized telemetry")
            parts = message.topic.split("/")
            frame = Telemetry.model_validate_json(message.payload)
            if (
                len(parts) != 3
                or parts[0] != "watertank"
                or parts[2] != "telemetry"
                or parts[1] != frame.device_id
            ):
                raise ValueError("Topic does not match the device identity")
            self.loop.call_soon_threadsafe(self._enqueue, frame)
        except (ValidationError, ValueError):
            self.rejected_messages += 1
            logger.warning("Rejected malformed MQTT telemetry")

    def _enqueue(self, frame: Telemetry):
        try:
            self.queue.put_nowait(frame)
        except asyncio.QueueFull:
            self.rejected_messages += 1
            logger.warning("MQTT ingestion queue is full; dropping telemetry")

    def publish(self, command: Command):
        # A simulator must never actuate physical hardware, even on a configured broker.
        if self.settings.app_mode != "live" or not self.client or not self.connected:
            return
        result = self.client.publish(
            f"watertank/{command.device_id}/command", command.model_dump_json(), qos=1, retain=False
        )
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            self.publish_failures += 1
            logger.warning("Could not queue valve command")

    async def close(self):
        if self.client:
            self.client.disconnect()
            await asyncio.to_thread(self.client.loop_stop)
        self.connected = False


class InfluxRecorder:
    def __init__(self, settings: Settings, recorder: Recorder):
        self.settings = settings
        self.recorder = recorder
        self.connected = False
        self.write_failures = 0
        self.stop_event = asyncio.Event()
        self.client = None
        self.writer = None
        if settings.influx_url:
            self.client = InfluxDBClient(
                url=settings.influx_url,
                token=settings.influx_token,
                org=settings.influx_org,
                timeout=3000,
                retries=0,
            )
            self.writer = self.client.write_api(write_options=SYNCHRONOUS)

    @staticmethod
    def point(snapshot: dict) -> Point:
        telemetry, decision = snapshot["telemetry"], snapshot["decision"]
        point = (
            Point("water_telemetry")
            .tag("device_id", telemetry["device_id"])
            .tag("flat_id", telemetry["flat_id"])
        )
        point.tag("source", snapshot["source"])
        for name in (
            "level_percent",
            "volume_l",
            "flow_lpm",
            "flow_out_lpm",
            "ultrasonic_distance_cm",
            "valve_percent",
        ):
            if telemetry[name] is not None:
                point.field(name, float(telemetry[name]))
        point.field("sensor_status", telemetry["sensor_status"])
        for name, value in decision.items():
            if value is not None:
                # A stable float type avoids field conflicts between 0 and 100%.
                point.field(
                    name,
                    float(value)
                    if isinstance(value, (int, float)) and not isinstance(value, bool)
                    else value,
                )
        return point.time(datetime.fromisoformat(telemetry["timestamp"]), WritePrecision.NS)

    def _flush(self):
        batch = self.recorder.pending()
        if batch:
            self.writer.write(
                bucket=self.settings.influx_bucket,
                record=[self.point(snapshot) for _, snapshot in batch],
            )
            self.recorder.mark_sent([row_id for row_id, _ in batch])
            self.connected = True
        else:
            self.connected = self.client.ping()

    async def run(self):
        if not self.client:
            return
        while not self.stop_event.is_set():
            try:
                await asyncio.to_thread(self._flush)
            except Exception as exc:
                self.connected = False
                self.write_failures += 1
                # Tokens and request payloads must never reach logs.
                if self.write_failures == 1 or self.write_failures % 30 == 0:
                    logger.warning(
                        "InfluxDB unavailable (%s); readings remain in the local recorder",
                        type(exc).__name__,
                    )
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=1 if self.connected else 5)
            except TimeoutError:
                pass

    def close(self):
        if self.writer:
            self.writer.close()
        if self.client:
            self.client.close()
