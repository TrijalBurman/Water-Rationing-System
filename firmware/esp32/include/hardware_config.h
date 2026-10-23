#pragma once

// Safe defaults for older private config.h files. Review the current example
// before enabling the changed two-tank wiring; these are not auto-detected.
#ifndef WATER_VALVE_ROLE_TRANSFER
#define WATER_VALVE_ROLE_TRANSFER 3
#endif
#ifndef WATER_FLOAT_ROLE_RECEIVER_FULL
#define WATER_FLOAT_ROLE_RECEIVER_FULL 1
#endif
#ifndef WATER_FLOAT_ROLE_SOURCE_LOW
#define WATER_FLOAT_ROLE_SOURCE_LOW 2
#endif
#ifndef WATER_FLOAT_ROLE
#define WATER_FLOAT_ROLE WATER_FLOAT_ROLE_RECEIVER_FULL
#endif
#ifndef WATER_RECEIVER_CAPACITY_L
#define WATER_RECEIVER_CAPACITY_L 1.5f
#endif
#ifndef WATER_HARDWARE_COMMISSIONED
#define WATER_HARDWARE_COMMISSIONED 0
#endif
#ifndef WATER_RELAY_ACTIVE_HIGH
#define WATER_RELAY_ACTIVE_HIGH 1
#endif
#ifndef WATER_FLOAT_RECOVERY_MS
#define WATER_FLOAT_RECOVERY_MS 500U
#endif
#ifndef WATER_TRIGGER_PULSE_US
#define WATER_TRIGGER_PULSE_US 20U
#endif
#ifndef WATER_SENSOR_MIN_CM
#define WATER_SENSOR_MIN_CM 30.0f
#endif
#ifndef WATER_SENSOR_MAX_CM
#define WATER_SENSOR_MAX_CM 300.0f
#endif
