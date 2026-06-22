# Implementation Plan

## 1. Problem Definition

Build an IoT and AI-based water management system that tracks tank water level,
monitors consumption, predicts time-to-depletion, detects abnormal flow loss, and
activates rationing when shortage risk becomes critical.

## 2. Physical Prototype

- Use two transparent containers to represent the main storage tank and consumer
  zone.
- Circulate water using a 5V or 12V submersible pump.
- Measure tank level using an HC-SR04 ultrasonic sensor.
- Measure consumption using a YF-S201 flow sensor.
- Control supply using a 12V solenoid valve.
- Use clear vinyl tubing so water movement is visible during the demo.

## 3. IoT and Cloud Flow

- ESP32 reads sensor values and publishes telemetry over MQTT.
- MQTT messages are ingested by AWS IoT Core or a local Mosquitto broker during
  development.
- Telemetry is stored in InfluxDB as time-series data.
- FastAPI processes readings, calculates status, and publishes actuator commands.

## 4. AI Analytics

- Start with an explainable linear time-to-depletion model for reliable demos.
- Use rolling flow averages and recent tank-level slope to estimate depletion.
- Add ARIMA or Prophet later if time-series sophistication is required for the
  report.

## 5. Dashboard and Demonstration

- Grafana shows tank percentage, flow rate, daily consumption, depletion time,
  system status, and alerts.
- Normal demo: stable tank level and normal supply status.
- Shortage demo: stop inlet flow and show predicted depletion time decreasing.
- Rationing demo: trigger solenoid valve when critical threshold is crossed.
- Leak demo: compare two flow sensors and show volume-loss alert.
