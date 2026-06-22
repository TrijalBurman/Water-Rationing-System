# Firmware

ESP32 firmware for the physical prototype.

Planned responsibilities:

- Read HC-SR04 ultrasonic distance and convert it to tank level percentage.
- Read YF-S201 pulse counts and convert them to flow rate.
- Publish telemetry over MQTT.
- Subscribe to rationing commands.
- Drive a relay or MOSFET module for the solenoid valve.
