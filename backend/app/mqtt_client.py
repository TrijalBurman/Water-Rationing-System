import json
import logging
from collections.abc import Callable

import paho.mqtt.client as mqtt

from app.config import Settings
from app.models import TelemetryReading, ValveCommand

logger = logging.getLogger(__name__)


class MqttService:
    def __init__(
        self,
        settings: Settings,
        on_telemetry: Callable[[TelemetryReading], None],
    ) -> None:
        self.settings = settings
        self.on_telemetry = on_telemetry
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

        if settings.mqtt_username:
            self.client.username_pw_set(settings.mqtt_username, settings.mqtt_password)

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def start(self) -> None:
        self.client.connect(self.settings.mqtt_host, self.settings.mqtt_port, keepalive=60)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def publish_valve_command(self, command: ValveCommand) -> None:
        payload = command.model_dump_json()
        self.client.publish(self.settings.mqtt_command_topic, payload, qos=1, retain=True)

    def _on_connect(self, client: mqtt.Client, _userdata, _flags, reason_code, _properties) -> None:
        if reason_code == 0:
            logger.info("Connected to MQTT broker at %s:%s", self.settings.mqtt_host, self.settings.mqtt_port)
            client.subscribe(self.settings.mqtt_telemetry_topic, qos=1)
            return
        logger.error("MQTT connection failed: %s", reason_code)

    def _on_message(self, _client: mqtt.Client, _userdata, message: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            self.on_telemetry(TelemetryReading.model_validate(payload))
        except Exception:
            logger.exception("Failed to process MQTT telemetry message")
