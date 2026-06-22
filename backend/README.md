# Backend

FastAPI backend for telemetry processing, forecasting, alert generation, and
MQTT control commands.

Planned responsibilities:

- Receive or subscribe to ESP32 telemetry.
- Store water level and flow-rate measurements.
- Calculate time-to-depletion.
- Detect leak/anomaly conditions.
- Publish solenoid valve commands.
- Expose API endpoints for dashboard and testing.
