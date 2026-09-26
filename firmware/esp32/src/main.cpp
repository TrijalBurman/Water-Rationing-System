#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <WiFi.h>

#include "config.h"

namespace {
constexpr uint32_t SAMPLE_INTERVAL_MS = 1000;
constexpr uint32_t PUBLISH_INTERVAL_MS = 5000;
constexpr uint32_t RATION_CYCLE_MS = 30000;
constexpr float MIN_VALID_DISTANCE_CM = 20.0f;
constexpr float MAX_VALID_DISTANCE_CM = 600.0f;

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
volatile uint32_t flowPulses = 0;
volatile uint32_t flowPulses2 = 0;
float commandedValvePercent = 100.0f;
bool sensorOk = false;
bool localLeakDetected = false;
uint8_t localLeakCycles = 0;
float latestDistanceCm = 0.0f;
float latestLevelPercent = 0.0f;
float latestVolumeLitres = 0.0f;
float latestFlowLpm = 0.0f;
float latestFlowOutLpm = 0.0f;
uint32_t lastSampleAt = 0;
uint32_t lastPublishAt = 0;
uint32_t previousFlowPulses = 0;
uint32_t previousFlowPulses2 = 0;

void IRAM_ATTR onFlowPulse() { ++flowPulses; }
void IRAM_ATTR onFlowPulse2() { ++flowPulses2; }

float medianDistanceCm() {
  constexpr size_t N = 5;
  float samples[N];
  for (size_t i = 0; i < N; ++i) {
    digitalWrite(ULTRASONIC_TRIG_PIN, LOW);
    delayMicroseconds(3);
    digitalWrite(ULTRASONIC_TRIG_PIN, HIGH);
    delayMicroseconds(20);  // JSN-SR04T requires at least a 10 us trigger.
    digitalWrite(ULTRASONIC_TRIG_PIN, LOW);
    unsigned long echoUs = pulseIn(ULTRASONIC_ECHO_PIN, HIGH, 40000);
    samples[i] = echoUs == 0 ? NAN : echoUs / 58.0f;
    delay(60);
  }
  // A failed echo is rejected rather than turning into an apparent empty tank.
  for (size_t i = 0; i < N; ++i) if (isnan(samples[i])) samples[i] = MAX_VALID_DISTANCE_CM + 1;
  for (size_t i = 1; i < N; ++i) {
    float value = samples[i];
    size_t j = i;
    while (j > 0 && samples[j - 1] > value) { samples[j] = samples[j - 1]; --j; }
    samples[j] = value;
  }
  return samples[N / 2];
}

void writeValveRelay(bool energized) {
  // Most opto-isolated relay boards are active-low; make this explicit in config.h.
  digitalWrite(VALVE_ON_OFF_PIN, (energized == VALVE_RELAY_ACTIVE_LOW) ? LOW : HIGH);
}

void setValve(float percent) {
  commandedValvePercent = constrain(percent, 0.0f, 100.0f);
  if (PROPORTIONAL_VALVE) {
    ledcWrite(0, static_cast<uint32_t>(255.0f * commandedValvePercent / 100.0f));
    return;
  }
  // For an ON/OFF valve, achieve rationing with a 30 s duty cycle. A flyback-protected
  // relay/MOSFET module is mandatory; use a motorized/proportional valve for smoother flow.
  uint32_t phase = millis() % RATION_CYCLE_MS;
  bool open = phase < (RATION_CYCLE_MS * commandedValvePercent / 100.0f);
  writeValveRelay(open);
}

void updateMeasurements() {
  latestDistanceCm = medianDistanceCm();
  sensorOk = latestDistanceCm >= MIN_VALID_DISTANCE_CM && latestDistanceCm <= MAX_VALID_DISTANCE_CM &&
             latestDistanceCm <= SENSOR_EMPTY_DISTANCE_CM + 5.0f;
  if (!sensorOk) {
    // Do not calculate a false level from a missing or out-of-range echo.
    setValve(min(commandedValvePercent, 30.0f));
    return;
  }
  float usableDistance = SENSOR_EMPTY_DISTANCE_CM - SENSOR_FULL_DISTANCE_CM;
  latestLevelPercent = constrain(100.0f * (SENSOR_EMPTY_DISTANCE_CM - latestDistanceCm) / usableDistance, 0.0f, 100.0f);
  latestVolumeLitres = TANK_CAPACITY_L * latestLevelPercent / 100.0f;
  if (latestLevelPercent < MIN_SAFE_PERCENT) setValve(0.0f);  // edge safety survives cloud loss

  noInterrupts();
  uint32_t pulses = flowPulses;
  uint32_t pulses2 = flowPulses2;
  interrupts();
  uint32_t delta = pulses - previousFlowPulses;
  previousFlowPulses = pulses;
  latestFlowLpm = (delta * 60.0f) / FLOW_PULSES_PER_LITER;  // 1 Hz sampling

  uint32_t delta2 = pulses2 - previousFlowPulses2;
  previousFlowPulses2 = pulses2;
  latestFlowOutLpm = (delta2 * 60.0f) / FLOW2_PULSES_PER_LITER;

  #if defined(EDGE_LEAK_DETECTION) && EDGE_LEAK_DETECTION
  float flowDiff = latestFlowLpm - latestFlowOutLpm;
  float leakThreshold = max(LEAK_DIFF_THRESHOLD_LPM, 0.15f * latestFlowLpm);
  if (flowDiff > leakThreshold && latestFlowLpm > 0.1f) {
    if (++localLeakCycles >= LEAK_CONFIRM_CYCLES) {
      localLeakDetected = true;
    }
  } else {
    localLeakCycles = 0;
    localLeakDetected = false;
  }
  if (localLeakDetected && commandedValvePercent > LEAK_THROTTLE_PERCENT) {
    setValve(LEAK_THROTTLE_PERCENT);
  }
  #endif
}

void ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void ensureMqtt() {
  if (!mqtt.connected() && WiFi.status() == WL_CONNECTED) {
    if (mqtt.connect(DEVICE_ID, MQTT_USERNAME, MQTT_PASSWORD)) {
      String commandTopic = String("watertank/") + DEVICE_ID + "/command";
      mqtt.subscribe(commandTopic.c_str(), 1);
    }
  }
}

void onCommand(char*, byte* payload, unsigned int length) {
  StaticJsonDocument<512> command;
  if (deserializeJson(command, payload, length)) return;
  float requested = command["valve_percent"] | commandedValvePercent;
  // Local minimum-reserve safety wins over remote command.
  if (sensorOk && latestLevelPercent < MIN_SAFE_PERCENT) requested = 0.0f;
  #if defined(EDGE_LEAK_DETECTION) && EDGE_LEAK_DETECTION
  if (localLeakDetected) requested = min(requested, LEAK_THROTTLE_PERCENT);
  #endif
  setValve(requested);
}

void publishTelemetry() {
  if (!mqtt.connected()) return;
  StaticJsonDocument<512> doc;
  doc["device_id"] = DEVICE_ID;
  doc["level_percent"] = serialized(String(latestLevelPercent, 2));
  doc["volume_l"] = serialized(String(latestVolumeLitres, 2));
  doc["flow_lpm"] = serialized(String(latestFlowLpm, 3));
  doc["flow_out_lpm"] = serialized(String(latestFlowOutLpm, 3));
  doc["ultrasonic_distance_cm"] = serialized(String(latestDistanceCm, 2));
  doc["sensor_status"] = sensorOk ? "ok" : "fault";
  doc["valve_percent"] = serialized(String(commandedValvePercent, 1));
  doc["leak_detected"] = localLeakDetected;
  doc["pump_on"] = false;
  doc["rssi"] = WiFi.RSSI();
  char body[512];
  size_t written = serializeJson(doc, body);
  String topic = String("watertank/") + DEVICE_ID + "/telemetry";
  mqtt.publish(topic.c_str(), reinterpret_cast<const uint8_t*>(body), written, false);
}
}  // namespace

void setup() {
  Serial.begin(115200);
  pinMode(ULTRASONIC_TRIG_PIN, OUTPUT);
  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);
  pinMode(ULTRASONIC_ECHO_PIN, INPUT);
  pinMode(FLOW_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(FLOW_PIN), onFlowPulse, RISING);
  #ifdef FLOW2_PIN
  pinMode(FLOW2_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(FLOW2_PIN), onFlowPulse2, RISING);
  #endif
  if (PROPORTIONAL_VALVE) {
    ledcSetup(0, 1000, 8);
    ledcAttachPin(VALVE_PWM_PIN, 0);
  } else {
    pinMode(VALVE_ON_OFF_PIN, OUTPUT);
    writeValveRelay(false);  // NC valve starts closed until the firmware decides otherwise.
  }
  setValve(100.0f);
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onCommand);
  ensureWifi();
}

void loop() {
  ensureWifi();
  ensureMqtt();
  mqtt.loop();
  uint32_t now = millis();
  if (now - lastSampleAt >= SAMPLE_INTERVAL_MS) { lastSampleAt = now; updateMeasurements(); }
  if (now - lastPublishAt >= PUBLISH_INTERVAL_MS) { lastPublishAt = now; publishTelemetry(); }
  if (!PROPORTIONAL_VALVE) setValve(commandedValvePercent);  // update duty-cycle phase
}
