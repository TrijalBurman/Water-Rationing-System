#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <WiFi.h>

const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* MQTT_HOST = "192.168.1.10";
const int MQTT_PORT = 1883;

const char* DEVICE_ID = "esp32-demo";
const char* TELEMETRY_TOPIC = "water/telemetry";
const char* COMMAND_TOPIC = "water/commands/valve";

const int TRIG_PIN = 5;
const int ECHO_PIN = 18;
const int FLOW_PIN = 27;
const int SOLENOID_PIN = 26;

const float TANK_HEIGHT_CM = 40.0;
const float FLOW_CALIBRATION_PULSES_PER_LITER = 450.0;

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

volatile unsigned long flowPulseCount = 0;
unsigned long lastPublishMs = 0;
unsigned long lastFlowSampleMs = 0;
float latestFlowLpm = 0.0;

void IRAM_ATTR countFlowPulse() {
  flowPulseCount++;
}

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.print("WiFi connected: ");
  Serial.println(WiFi.localIP());
}

float readDistanceCm() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long duration = pulseIn(ECHO_PIN, HIGH, 30000);
  if (duration <= 0) {
    return TANK_HEIGHT_CM;
  }

  return duration * 0.0343 / 2.0;
}

float readTankLevelPercent() {
  float distanceCm = readDistanceCm();
  float waterHeightCm = TANK_HEIGHT_CM - distanceCm;
  float level = (waterHeightCm / TANK_HEIGHT_CM) * 100.0;
  return constrain(level, 0.0, 100.0);
}

void updateFlowRate() {
  unsigned long now = millis();
  unsigned long elapsedMs = now - lastFlowSampleMs;
  if (elapsedMs < 1000) {
    return;
  }

  noInterrupts();
  unsigned long pulses = flowPulseCount;
  flowPulseCount = 0;
  interrupts();

  float liters = pulses / FLOW_CALIBRATION_PULSES_PER_LITER;
  latestFlowLpm = liters * (60000.0 / elapsedMs);
  lastFlowSampleMs = now;
}

void applyValveState(const char* state) {
  if (strcmp(state, "closed") == 0 || strcmp(state, "restricted") == 0) {
    digitalWrite(SOLENOID_PIN, HIGH);
    Serial.println("Solenoid activated for rationing.");
  } else {
    digitalWrite(SOLENOID_PIN, LOW);
    Serial.println("Solenoid released. Valve open.");
  }
}

void onMqttMessage(char* topic, byte* payload, unsigned int length) {
  if (strcmp(topic, COMMAND_TOPIC) != 0) {
    return;
  }

  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, payload, length);
  if (error) {
    Serial.println("Failed to parse valve command.");
    return;
  }

  const char* state = doc["state"] | "open";
  applyValveState(state);
}

void connectMqtt() {
  while (!mqttClient.connected()) {
    Serial.print("Connecting to MQTT...");
    if (mqttClient.connect(DEVICE_ID)) {
      Serial.println("connected");
      mqttClient.subscribe(COMMAND_TOPIC);
    } else {
      Serial.print("failed, rc=");
      Serial.print(mqttClient.state());
      Serial.println(" retrying in 2 seconds");
      delay(2000);
    }
  }
}

void publishTelemetry() {
  JsonDocument doc;
  doc["device_id"] = DEVICE_ID;
  doc["tank_level_percent"] = readTankLevelPercent();
  doc["flow_lpm"] = latestFlowLpm;
  doc["downstream_flow_lpm"] = latestFlowLpm;

  char buffer[256];
  size_t length = serializeJson(doc, buffer);
  mqttClient.publish(TELEMETRY_TOPIC, buffer, length);

  Serial.print("Published telemetry: ");
  Serial.println(buffer);
}

void setup() {
  Serial.begin(115200);

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(FLOW_PIN, INPUT_PULLUP);
  pinMode(SOLENOID_PIN, OUTPUT);
  digitalWrite(SOLENOID_PIN, LOW);

  attachInterrupt(digitalPinToInterrupt(FLOW_PIN), countFlowPulse, RISING);

  connectWifi();
  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  mqttClient.setCallback(onMqttMessage);
  lastFlowSampleMs = millis();
}

void loop() {
  if (!mqttClient.connected()) {
    connectMqtt();
  }

  mqttClient.loop();
  updateFlowRate();

  if (millis() - lastPublishMs >= 5000) {
    publishTelemetry();
    lastPublishMs = millis();
  }
}
