import json
import logging
from collections.abc import Callable

import paho.mqtt.client as mqtt

from .schemas import Decision, Telemetry
from .settings import Settings

logger = logging.getLogger(__name__)


class MqttBridge:
    def __init__(self, settings: Settings, on_telemetry: Callable[[Telemetry], Decision]):
        self.settings = settings
        self.on_telemetry = on_telemetry
        self.connected = False
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="water-rationing-api")
        if settings.mqtt_username and settings.mqtt_password:
            self.client.username_pw_set(settings.mqtt_username, settings.mqtt_password)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    def start(self) -> None:
        try:
            self.client.connect_async(self.settings.mqtt_host, self.settings.mqtt_port, keepalive=30)
            self.client.loop_start()
        except Exception:
            logger.exception("MQTT start failed; REST ingestion remains available")

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def publish_command(self, decision: Decision) -> None:
        payload = decision.model_dump(mode="json")
        self.client.publish(f"watertank/{decision.device_id}/command", json.dumps(payload), qos=1, retain=True)

    def _on_connect(self, client: mqtt.Client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            logger.error("MQTT connection rejected: %s", reason_code)
            return
        self.connected = True
        client.subscribe("watertank/+/telemetry", qos=1)
        logger.info("Connected to MQTT broker")

    def _on_disconnect(self, client: mqtt.Client, userdata, disconnect_flags, reason_code, properties) -> None:
        self.connected = False
        if reason_code:
            logger.warning("Disconnected from MQTT: %s", reason_code)

    def _on_message(self, client: mqtt.Client, userdata, message: mqtt.MQTTMessage) -> None:
        try:
            telemetry = Telemetry.model_validate_json(message.payload)
            decision = self.on_telemetry(telemetry)
            self.publish_command(decision)
        except Exception:
            logger.exception("Rejected malformed telemetry from %s", message.topic)

