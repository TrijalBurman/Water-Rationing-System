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

## Run Locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Useful endpoints:

- `GET /health`
- `POST /telemetry`
- `GET /status`
- `GET /readings`
- `POST /commands/valve`
- `POST /demo/reset`

Run tests:

```bash
pytest
```
