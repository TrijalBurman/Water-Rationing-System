#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>
#include <sys/time.h>
#include <time.h>

#ifdef WATER_HAS_LOCAL_CONFIG
#include "../include/config.h"
#else
#include "config.example.h"
#endif
#include "control_logic.h"

namespace {
constexpr uint8_t kTriggerPin = 26;
constexpr uint8_t kEchoPin = 34;
constexpr uint8_t kFlowInPin = 27;
constexpr uint8_t kFlowOutPin = 32;
constexpr uint8_t kRelayPin = 25;
constexpr uint32_t kEchoTimeoutUs = 40000U;
constexpr uint32_t kSampleIntervalMs = 120U;
constexpr uint32_t kTelemetryIntervalMs = 1000U;
constexpr int64_t kEarliestUnixSeconds = 1704067200LL;  // 2024-01-01 UTC

static_assert(WATER_TANK_CAPACITY_L > 0 && WATER_TANK_USABLE_HEIGHT_CM > 0, "Tank calibration must be positive");
static_assert(WATER_PROBE_STANDOFF_CM >= 25.0f && WATER_PROBE_STANDOFF_CM + WATER_TANK_USABLE_HEIGHT_CM <= 600.0f, "Tank geometry must respect probe clearance and range");
static_assert(WATER_FLOW_IN_PULSES_PER_LITRE > 0 && WATER_FLOW_OUT_PULSES_PER_LITRE > 0, "Flow calibration must be positive");
static_assert(sizeof(WATER_DEVICE_ID) > 1 && sizeof(WATER_DEVICE_ID) <= 65, "Device ID must contain 1..64 characters");
static_assert(WATER_VALVE_ROLE == WATER_VALVE_ROLE_MASTER || WATER_VALVE_ROLE == WATER_VALVE_ROLE_FLAT, "Select the installed relay role");
static_assert(WATER_COMMAND_TIMEOUT_MS > 0 && WATER_COMMAND_TIMEOUT_MS <= 30000U, "Command timeout must be 1..30000ms");
static_assert(WATER_COMMAND_MAX_TTL_MS > 0 && WATER_COMMAND_MAX_TTL_MS <= 30000, "Command TTL must be 1..30000ms");

struct Command {
  float percent;
  uint32_t receivedAtMs;
  int64_t expiresAtMs;
};

struct Telemetry {
  int64_t timestampMs;
  float levelPercent;
  float flowInLpm;
  float flowOutLpm;
  float distanceCm;
  float valvePercent;
  bool sensorFault;
};

QueueHandle_t commandQueue;
QueueHandle_t telemetryQueue;
water::ValveController controller(WATER_COMMAND_TIMEOUT_MS);
portMUX_TYPE sensorMux = portMUX_INITIALIZER_UNLOCKED;
volatile uint32_t flowInPulses = 0;
volatile uint32_t flowOutPulses = 0;
volatile uint32_t echoRiseUs = 0;
volatile uint32_t echoDurationUs = 0;
volatile bool echoArmed = false;
volatile bool echoRisen = false;
volatile bool echoDone = false;
bool waitingForEcho = false;
uint32_t triggerStartedUs = 0;
uint32_t lastSampleMs = 0;
uint32_t lastTelemetryMs = 0;
float latestDistanceCm = NAN;

#if WATER_MQTT_TLS
WiFiClientSecure networkClient;
#else
WiFiClient networkClient;
#endif
PubSubClient mqtt(networkClient);
char telemetryTopic[128];
char commandTopic[128];
int64_t sessionStartedMs = 0;
int64_t lastIssuedMs = 0;
char lastCommandId[97]{};

int64_t unixMillis() {
  timeval now{};
  gettimeofday(&now, nullptr);
  if (now.tv_sec < kEarliestUnixSeconds) return 0;
  return static_cast<int64_t>(now.tv_sec) * 1000 + now.tv_usec / 1000;
}

void IRAM_ATTR onFlowIn() {
  portENTER_CRITICAL_ISR(&sensorMux);
  ++flowInPulses;
  portEXIT_CRITICAL_ISR(&sensorMux);
}

void IRAM_ATTR onFlowOut() {
  portENTER_CRITICAL_ISR(&sensorMux);
  ++flowOutPulses;
  portEXIT_CRITICAL_ISR(&sensorMux);
}

void IRAM_ATTR onEcho() {
  const uint32_t nowUs = micros();
  const bool high = digitalRead(kEchoPin) == HIGH;
  portENTER_CRITICAL_ISR(&sensorMux);
  if (echoArmed) {
    if (high) {
      echoRiseUs = nowUs;
      echoRisen = true;
    } else if (echoRisen) {
      echoDurationUs = nowUs - echoRiseUs;
      echoDone = true;
      echoArmed = false;
    }
  }
  portEXIT_CRITICAL_ISR(&sensorMux);
}

void serviceUltrasonic(uint32_t nowMs) {
  if (waitingForEcho) {
    uint32_t pulseUs = 0;
    bool complete = false;
    const bool timedOut = static_cast<uint32_t>(micros() - triggerStartedUs) >= kEchoTimeoutUs;
    portENTER_CRITICAL(&sensorMux);
    complete = echoDone;
    if (complete) pulseUs = echoDurationUs;
    if (complete || timedOut) {
      echoArmed = false;
      echoDone = false;
    }
    portEXIT_CRITICAL(&sensorMux);
    if (complete || timedOut) {
      waitingForEcho = false;
      latestDistanceCm = complete ? pulseUs * 0.0343f / 2.0f : NAN;
      controller.sample(latestDistanceCm, WATER_PROBE_STANDOFF_CM, WATER_TANK_USABLE_HEIGHT_CM);
    }
  }
  if (!waitingForEcho && static_cast<uint32_t>(nowMs - lastSampleMs) >= kSampleIntervalMs) {
    lastSampleMs = nowMs;
    portENTER_CRITICAL(&sensorMux);
    echoArmed = true;
    echoRisen = false;
    echoDone = false;
    portEXIT_CRITICAL(&sensorMux);
    triggerStartedUs = micros();
    waitingForEcho = true;
    digitalWrite(kTriggerPin, HIGH);
    delayMicroseconds(10);  // Only the 10us trigger blocks; echo capture uses ISR.
    digitalWrite(kTriggerPin, LOW);
  }
}

bool validPercent(JsonVariantConst value) {
  return value.is<float>() && std::isfinite(value.as<float>()) &&
         value.as<float>() >= 0.0f && value.as<float>() <= 100.0f;
}

void onCommand(char* topic, byte* payload, unsigned int length) {
  if (std::strcmp(topic, commandTopic) != 0 || length > 1536) return;
  StaticJsonDocument<2048> doc;
  if (deserializeJson(doc, static_cast<const byte*>(payload), length)) return;
  const char* deviceId = doc["device_id"] | "";
  const char* commandId = doc["command_id"] | "";
  const char* mode = doc["mode"] | "";
  const char* tankMode = doc["tank_mode"] | "";
  const char* flatStatus = doc["flat_status"] | "";
  if (std::strcmp(deviceId, WATER_DEVICE_ID) != 0 || !*commandId || std::strlen(commandId) > 96 ||
      !*mode || !*tankMode || !*flatStatus || std::strcmp(commandId, lastCommandId) == 0 ||
      !validPercent(doc["master_valve_percent"]) || !validPercent(doc["flat_valve_percent"])) return;
  const int64_t issued = water::parseUtcMillis(doc["issued_at"] | "");
  const int64_t expires = water::parseUtcMillis(doc["expires_at"] | "");
  if (!water::commandFresh(issued, expires, unixMillis(), sessionStartedMs,
                           lastIssuedMs, WATER_COMMAND_MAX_TTL_MS)) return;
#if WATER_VALVE_ROLE == WATER_VALVE_ROLE_MASTER
  float percent = doc["master_valve_percent"].as<float>();
#else
  float percent = doc["flat_valve_percent"].as<float>();
#endif
  if (std::strcmp(mode, "CRITICAL") == 0 || std::strcmp(tankMode, "CRITICAL") == 0) percent = 0.0f;
  const Command command{percent, millis(), expires};
  xQueueOverwrite(commandQueue, &command);
  lastIssuedMs = issued;
  strlcpy(lastCommandId, commandId, sizeof(lastCommandId));
}

void publishTelemetry(const Telemetry& frame) {
  if (frame.timestampMs <= 0) return;
  const time_t seconds = frame.timestampMs / 1000;
  tm utc{};
  gmtime_r(&seconds, &utc);
  char timestamp[32];
  strftime(timestamp, sizeof(timestamp), "%Y-%m-%dT%H:%M:%SZ", &utc);
  StaticJsonDocument<768> doc;
  doc["device_id"] = WATER_DEVICE_ID;
  doc["flat_id"] = WATER_FLAT_ID;
  doc["timestamp"] = timestamp;
  doc["level_percent"] = frame.levelPercent;
  doc["volume_l"] = frame.levelPercent * WATER_TANK_CAPACITY_L / 100.0f;
  doc["flow_lpm"] = frame.flowInLpm;
  doc["flow_out_lpm"] = frame.flowOutLpm;
  if (std::isfinite(frame.distanceCm)) doc["ultrasonic_distance_cm"] = frame.distanceCm;
  else doc["ultrasonic_distance_cm"] = nullptr;
  doc["sensor_status"] = frame.sensorFault ? "fault" : "ok";
  doc["valve_percent"] = frame.valvePercent;
  char payload[768];
  const size_t bytes = serializeJson(doc, payload, sizeof(payload));
  // PubSubClient publishes QoS 0. Telemetry is best effort and never retained.
  mqtt.publish(telemetryTopic, reinterpret_cast<const uint8_t*>(payload), bytes, false);
}

void networkTask(void*) {
  if (std::strcmp(WATER_WIFI_SSID, "CHANGE_ME") == 0 || std::strcmp(WATER_MQTT_PASSWORD, "CHANGE_ME") == 0) {
    Serial.println("Configure include/config.h; networking disabled and valve closed.");
    vTaskDelete(nullptr);
    return;
  }
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WATER_WIFI_SSID, WATER_WIFI_PASSWORD);
  configTime(0, 0, WATER_NTP_SERVER);
#if WATER_MQTT_TLS
  networkClient.setCACert(WATER_MQTT_CA_CERT);
  networkClient.setHandshakeTimeout(5);
#endif
  mqtt.setServer(WATER_MQTT_HOST, WATER_MQTT_PORT);
  mqtt.setCallback(onCommand);
  mqtt.setKeepAlive(15);
  mqtt.setSocketTimeout(1);
  if (!mqtt.setBufferSize(2048)) {
    Serial.println("MQTT buffer allocation failed; networking disabled.");
    vTaskDelete(nullptr);
    return;
  }
  uint32_t lastWifiAttemptMs = millis();
  uint32_t lastMqttAttemptMs = millis() - 5000U;
  for (;;) {
    const uint32_t nowMs = millis();
    if (WiFi.status() != WL_CONNECTED) {
      if (mqtt.connected()) mqtt.disconnect();
      if (static_cast<uint32_t>(nowMs - lastWifiAttemptMs) >= 15000U) {
        lastWifiAttemptMs = nowMs;
        WiFi.reconnect();
      }
    } else if (unixMillis() > 0) {
      if (!mqtt.connected() && static_cast<uint32_t>(nowMs - lastMqttAttemptMs) >= 5000U) {
        lastMqttAttemptMs = nowMs;
        if (mqtt.connect(WATER_DEVICE_ID, WATER_MQTT_USERNAME, WATER_MQTT_PASSWORD)) {
          // Set after CONNECT, before SUBSCRIBE. Even unexpired retained commands
          // from before this session cannot open the valve after a reboot.
          sessionStartedMs = unixMillis();
          if (!mqtt.subscribe(commandTopic, 1)) mqtt.disconnect();
        }
      }
      if (mqtt.connected()) {
        mqtt.loop();
        Telemetry frame{};
        if (xQueueReceive(telemetryQueue, &frame, 0) == pdTRUE) {
          const int64_t ageMs = unixMillis() - frame.timestampMs;
          if (ageMs >= 0 && ageMs < 2000) publishTelemetry(frame);
        }
      }
    }
    vTaskDelay(pdMS_TO_TICKS(10));
  }
}
}  // namespace

void setup() {
  // Latch inactive HIGH before switching GPIO to output. A physical pull-up on
  // the relay input is still necessary to hold it off while the ESP32 resets.
  digitalWrite(kRelayPin, HIGH);
  pinMode(kRelayPin, OUTPUT);
  digitalWrite(kTriggerPin, LOW);
  pinMode(kTriggerPin, OUTPUT);
  pinMode(kEchoPin, INPUT);
  pinMode(kFlowInPin, INPUT);
  pinMode(kFlowOutPin, INPUT);
  Serial.begin(115200);
  attachInterrupt(digitalPinToInterrupt(kEchoPin), onEcho, CHANGE);
  attachInterrupt(digitalPinToInterrupt(kFlowInPin), onFlowIn, RISING);
  attachInterrupt(digitalPinToInterrupt(kFlowOutPin), onFlowOut, RISING);
  commandQueue = xQueueCreate(1, sizeof(Command));
  telemetryQueue = xQueueCreate(1, sizeof(Telemetry));
  if (!commandQueue || !telemetryQueue) {
    Serial.println("Queue allocation failed; valve held closed.");
    while (true) delay(1000);
  }
  snprintf(telemetryTopic, sizeof(telemetryTopic), "watertank/%s/telemetry", WATER_DEVICE_ID);
  snprintf(commandTopic, sizeof(commandTopic), "watertank/%s/command", WATER_DEVICE_ID);
  // Arduino's loop runs on core 1. DNS, MQTT and TLS waits run on core 0.
  if (xTaskCreatePinnedToCore(networkTask, "water-network", 8192, nullptr, 1, nullptr, 0) != pdPASS)
    Serial.println("Network task allocation failed; no commands will be accepted.");
}

void loop() {
  const uint32_t nowMs = millis();
  serviceUltrasonic(nowMs);
  Command command{};
  if (xQueueReceive(commandQueue, &command, 0) == pdTRUE)
    controller.command(command.percent, command.receivedAtMs, command.expiresAtMs);
  const int64_t currentUnixMs = unixMillis();
  digitalWrite(kRelayPin, controller.relayOpen(nowMs, currentUnixMs) ? LOW : HIGH);

  if (static_cast<uint32_t>(nowMs - lastTelemetryMs) >= kTelemetryIntervalMs) {
    const uint32_t elapsedMs = nowMs - lastTelemetryMs;
    lastTelemetryMs = nowMs;
    uint32_t inflow = 0, outflow = 0;
    portENTER_CRITICAL(&sensorMux);
    inflow = flowInPulses; outflow = flowOutPulses;
    flowInPulses = 0; flowOutPulses = 0;
    portEXIT_CRITICAL(&sensorMux);
    const float flowIn = inflow * 60000.0f / (WATER_FLOW_IN_PULSES_PER_LITRE * elapsedMs);
    const float flowOut = outflow * 60000.0f / (WATER_FLOW_OUT_PULSES_PER_LITRE * elapsedMs);
    // On faults retain the last trusted level for reserve protection; no echo
    // remains null, and sensor_status always flags that level as stale.
    const float distance = controller.sensorFault() ? latestDistanceCm : controller.medianDistanceCm();
    const Telemetry frame{currentUnixMs, controller.levelPercent(), flowIn, flowOut,
                          distance, controller.effectivePercent(nowMs, currentUnixMs), controller.sensorFault()};
    if (currentUnixMs > 0) xQueueOverwrite(telemetryQueue, &frame);
  }
  delay(1);
}
