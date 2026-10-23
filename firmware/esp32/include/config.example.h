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

// One physical relay is wired by the plan. Select exactly the installed role.
#define WATER_VALVE_ROLE_MASTER 1
#define WATER_VALVE_ROLE_FLAT 2
#define WATER_VALVE_ROLE WATER_VALVE_ROLE_MASTER

#define WATER_TANK_CAPACITY_L 200.0f
// Depth of usable water, excluding the probe standoff above the full level.
#define WATER_TANK_USABLE_HEIGHT_CM 150.0f
#define WATER_PROBE_STANDOFF_CM 25.0f
#define WATER_FLOW_IN_PULSES_PER_LITRE 450.0f
#define WATER_FLOW_OUT_PULSES_PER_LITRE 450.0f
#define WATER_COMMAND_TIMEOUT_MS 10000U
#define WATER_COMMAND_MAX_TTL_MS 30000LL

// TLS must be configured at the broker too (normally port 8883).
// For TLS, set this to 1, change WATER_MQTT_PORT and paste the broker CA below.
// Certificate checks are never disabled. Plain MQTT is for a trusted lab LAN.
#define WATER_MQTT_TLS 0
static const char WATER_MQTT_CA_CERT[] = R"PEM(
-----BEGIN CERTIFICATE-----
PASTE_YOUR_BROKER_CA_CERTIFICATE_HERE
-----END CERTIFICATE-----
)PEM";
