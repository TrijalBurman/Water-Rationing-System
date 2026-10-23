#pragma once

// Copy to config.h and set real credentials before flashing hardware.
// The example builds, but networking stays disabled until these are changed.
#define WATER_WIFI_SSID "CHANGE_ME"
#define WATER_WIFI_PASSWORD "CHANGE_ME"
#define WATER_MQTT_HOST "192.168.1.10"
#define WATER_MQTT_PORT 1883
#define WATER_MQTT_USERNAME "tank-01"
#define WATER_MQTT_PASSWORD "CHANGE_ME"
#define WATER_DEVICE_ID "tank-01"
#define WATER_FLAT_ID "101"
#define WATER_NTP_SERVER "pool.ntp.org"

// One installed valve, on channel 1 of the Robu 1121234 two-channel relay.
// TRANSFER applies the stricter source/pipe limit to that one physical valve.
#define WATER_VALVE_ROLE_MASTER 1
#define WATER_VALVE_ROLE_FLAT 2
#define WATER_VALVE_ROLE_TRANSFER 3
#define WATER_VALVE_ROLE WATER_VALVE_ROLE_TRANSFER

#define WATER_TANK_CAPACITY_L 2.5f
#define WATER_RECEIVER_CAPACITY_L 1.5f
// Depth of usable water, excluding the probe standoff above the full level.
#define WATER_TANK_USABLE_HEIGHT_CM 20.0f  // User's approximate depth; measure/calibrate.
#define WATER_PROBE_STANDOFF_CM 30.0f     // Mount probe this far above FULL water.
#define WATER_SENSOR_MIN_CM 30.0f        // Conservative project bounds, not a revision ID.
#define WATER_SENSOR_MAX_CM 300.0f
#define WATER_TRIGGER_PULSE_US 20U       // AJ-SR04M ordinary PWM mode, R19 open.
#define WATER_FLOW_IN_PULSES_PER_LITRE 450.0f
#define WATER_FLOW_OUT_PULSES_PER_LITRE 450.0f
#define WATER_COMMAND_TIMEOUT_MS 10000U
#define WATER_COMMAND_MAX_TTL_MS 30000LL

// Keep 0 until the wiring, float orientation, measured geometry, safe GPIO
// interfaces, proper 12V supply and pressure-compatible plumbing are checked.
// Two PP3 9V batteries cannot substitute for the valve's 12V/1A supply, and
// Robu 31396 is explicitly unsuitable for gravity-fed operation.
#define WATER_HARDWARE_COMMISSIONED 0
// Set BOTH relay channel jumpers to HIGH trigger. IN2/GPIO23 stays inactive.
#define WATER_RELAY_ACTIVE_HIGH 1
// GPIO33 -> dry float contact -> GND. Closed=permit; open/full/broken wire=stop.
#define WATER_FLOAT_ROLE_RECEIVER_FULL 1
#define WATER_FLOAT_ROLE_SOURCE_LOW 2
#define WATER_FLOAT_ROLE WATER_FLOAT_ROLE_RECEIVER_FULL
#define WATER_FLOAT_RECOVERY_MS 500U

// TLS must be configured at the broker too (normally port 8883).
// For TLS, set this to 1, change WATER_MQTT_PORT and paste the broker CA below.
// Certificate checks are never disabled. Plain MQTT is for a trusted lab LAN.
#define WATER_MQTT_TLS 0
static const char WATER_MQTT_CA_CERT[] = R"PEM(
-----BEGIN CERTIFICATE-----
PASTE_YOUR_BROKER_CA_CERTIFICATE_HERE
-----END CERTIFICATE-----
)PEM";
