# Firmware

ESP32 firmware for the physical prototype.

Planned responsibilities:

- Read HC-SR04 ultrasonic distance and convert it to tank level percentage.
- Read YF-S201 pulse counts and convert them to flow rate.
- Publish telemetry over MQTT.
- Subscribe to rationing commands.
- Drive a relay or MOSFET module for the solenoid valve.

## Setup

This firmware is a PlatformIO project.

1. Open `firmware/` in VS Code with the PlatformIO extension.
2. Edit WiFi and MQTT values in `src/main.cpp`.
3. Connect the ESP32 board.
4. Build and upload the `esp32dev` environment.

Default pins:

- HC-SR04 TRIG: GPIO 5
- HC-SR04 ECHO: GPIO 18
- YF-S201 signal: GPIO 27
- Solenoid relay/MOSFET signal: GPIO 26
