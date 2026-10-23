# WaterWise · Smart Water Management

An implementation of the supplied [system plan](implementation_plan.md): ESP32 sensing and valve control, a FastAPI decision service, an authenticated MQTT broker, InfluxDB history, Grafana operations dashboard, and a responsive resident/admin portal.

## Run the working demo

Requires Python 3.12+ and an internet connection for the first dependency install. All local environments, downloads, caches, and data stay in this project directory.

For step-by-step instructions using the restored `/run/media/trijal/HDD/FinalYearProjectByAstra` location, see the [getting started guide](docs/getting-started.md).

```bash
./scripts/setup.sh
./scripts/run-demo.sh
```

Open **http://127.0.0.1:8000**. If that port is busy, use `PORT=8010 ./scripts/run-demo.sh` and open **http://127.0.0.1:8010**. The portal needs no frontend build step or external CDN. API documentation is at `/docs`.

The simulator produces a reading every second. In the portal's admin view, switch among normal supply, a supply warning, rationing, protected reserve, a branch leak, sensor failure, and recovery. The three-sample leak check and five-sample forecast may take a few readings to settle after a change. All displayed history and daily consumption come from readings recorded by the backend.

The local demo binds only to the local machine and needs no API key. It does not send MQTT valve commands. The deployment configuration generates an API key for changes made through the portal or API.

## Included

| Component | Location | What it does |
| --- | --- | --- |
| Controller and API | `backend/` | Forecasts reserve depletion, detects branch leaks, issues expiring commands, records history and daily use |
| Resident/admin portal | `frontend/` | Live tank and quota indicators, flow history, leak alerts, hardware status, simulator controls |
| ESP32 firmware | `firmware/esp32/` | JSN-SR04T median filtering, two flow meters, independent reserve protection, 30-second valve duty cycle |
| Deployment | `compose.yaml`, `scripts/bootstrap.sh` | FastAPI, Mosquitto 2.0, InfluxDB 2.7, Grafana 11.4 |
| Flight recorder | `grafana/dashboards/water-rationing.json` | Eight provisioned panels, refreshing every five seconds |
| Verification | `tests/`, `firmware/esp32/test-native.sh` | Controller, API, persistence, and native firmware safety tests |

## Controller behavior

The protected reserve is 10% of configured capacity (20 L for a 200 L tank). The average of the last five delivery-inlet flow readings predicts minutes to reserve.

| Tank condition, evaluated in order | Master valve duty |
| --- | --- |
| Below 10% reserve | 0% |
| Invalid ultrasonic reading | At most 30% |
| Level below 25%, or forecast below 60 minutes | `max(20, level_percent)`% |
| Forecast from 60 to below 120 minutes | 100%, warning |
| Otherwise | 100% |

A branch imbalance above `max(0.3 L/min, 15% of inlet flow)` for three consecutive readings limits the branch valve to 25%. The first two readings show `SUSPECTED_LEAK`. A balanced reading clears the leak state. Branch restriction never opens a valve beyond a stricter tank limit. Reserve protection closes both commanded valves.

**The two meters must straddle the delivery branch.** The first measures withdrawal from the tank into the branch, not refill into the tank. Comparing tank refill with apartment consumption cannot isolate a pipeline leak. See the [architecture notes](docs/architecture.md) for assumptions and the gaps resolved in the original plan.

## Deploy the full stack

```bash
./scripts/bootstrap.sh
docker compose up --build -d
```

See [deployment instructions](docs/deployment.md) for credentials, Grafana, LAN access, and switching to physical telemetry. Docker manages images and named data volumes in its own storage, so those two commands are separate from the workspace-contained local demo.

## Connect hardware

Read the [hardware and commissioning guide](docs/hardware.md) before wiring and the [firmware guide](firmware/README.md) before flashing. Copy `firmware/esp32/include/config.example.h` to `config.h`, configure credentials and calibration, then use the firmware build script.

Only the JSN-SR04T is used. GPIO pins match the supplied plan. The original plan specifies one relay while describing separate master and branch valves; select the installed valve's role in firmware. Independent actuation requires separately wired actuators and an expanded control topology. There is no pump contactor or pump output in the provided pinout.

## Verify

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check backend tests
./firmware/esp32/test-native.sh
```

Test files, temporary databases, and caches remain under this directory. See [verification notes](docs/verification.md) for completed checks and hardware/deployment checks that still require their target environment.

## API at a glance

| Route | Purpose |
| --- | --- |
| `POST /telemetry` | Validate a reading and return the controller decision |
| `GET /health` | Service status and ingestion/write counters |
| `GET /health/ready` | HTTP 503 when a configured dependency is unavailable |
| `GET /devices/{device_id}/latest` | Reading, decision, freshness, and today's quota |
| `GET /devices/{device_id}/history?minutes=60` | Chart data; at most 1,500 points |
| `GET /api/overview` | Device summaries and service status |
| `GET /api/demo` | Simulator state and available scenarios |
| `POST /api/demo` | Start, stop, choose a scenario, or reset local demo history |

Write routes require `X-API-Key` when `API_KEY` is configured. Reads are intended for a trusted local deployment. Demo controls are unavailable in live mode. See [API examples](docs/api.md).

The forecasting algorithm is the deterministic rolling average specified in the plan. This project does not claim to contain a trained machine-learning model or a validated consumption prediction model.
