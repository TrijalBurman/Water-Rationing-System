#pragma once

// Copy this file to config.h and set values for the local network and broker.
#define WIFI_SSID "replace-me"
#define WIFI_PASSWORD "replace-me"
#define MQTT_HOST "192.168.1.10"
#define MQTT_PORT 1883
#define MQTT_USERNAME "water-device"
#define MQTT_PASSWORD "replace-me"
#define DEVICE_ID "tank-01"

// Tank-specific calibration. Measure these values after installing the probe.
#define TANK_CAPACITY_L 200.0f
#define MIN_SAFE_PERCENT 10.0f
#define SENSOR_EMPTY_DISTANCE_CM 60.0f
#define SENSOR_FULL_DISTANCE_CM 25.0f

// JSN-SR04T V3.0: power at 5 V. Its Echo pin must go through a 1k/2k
// divider before reaching this 3.3 V ESP32 input.
#define ULTRASONIC_TRIG_PIN 26
#define ULTRASONIC_ECHO_PIN 34

// Flow sensor 1 (Inflow / Tank outlet) - 5V powered with 1k/2k divider to 3.3V
#define FLOW_PIN 27
#define FLOW_PULSES_PER_LITER 450.0f

// Flow sensor 2 (Outflow / Consumer end) - 5V powered with 1k/2k divider to 3.3V
#define FLOW2_PIN 32
#define FLOW2_PULSES_PER_LITER 450.0f

// Edge leak safety (local fail-safe throttling if network/MQTT is unavailable)
#define EDGE_LEAK_DETECTION true
#define LEAK_DIFF_THRESHOLD_LPM 0.3f
#define LEAK_CONFIRM_CYCLES 3
#define LEAK_THROTTLE_PERCENT 25.0f

// The demonstration valve is normally-closed and only ON/OFF, so rationing is
// implemented as a timed 30-second duty cycle. Change to true only with an
// actual proportional-valve controller.
#define PROPORTIONAL_VALVE false
#define VALVE_PWM_PIN 25
#define VALVE_ON_OFF_PIN 25
#define VALVE_RELAY_ACTIVE_LOW true
