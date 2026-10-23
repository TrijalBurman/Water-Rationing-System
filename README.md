# WaterWise · Smart Water Management

A water-transfer monitor for the owned **2.5 L source tank and 1.5 L receiver**: ESP32 sensing, local float protection, one valve, a FastAPI decision service, authenticated MQTT, InfluxDB history, Grafana, and a resident/admin portal. The [original plan](implementation_plan.md) provides the control algorithm; the current [hardware guide](docs/hardware.md) describes the actual components.

## Run the working demo

This **`windows` branch** includes native Windows setup, launchers, credential bootstrap, firmware tooling, and browser checks. The original published baseline is on [`trijal`](https://github.com/TrijalBurman/Water-Rationing-System/tree/trijal). Hardware connections are the same on both branches.

Requires Python 3.12+ and an internet connection for the first dependency install. The local demo runs directly on Windows without Docker, Git Bash, or a WSL shell. Local environments, downloads, caches, and data stay in this project directory.

In **PowerShell**:

```powershell
git clone --branch windows https://github.com/TrijalBurman/Water-Rationing-System.git
Set-Location .\Water-Rationing-System
py -3.12 scripts/manage.py setup
py -3.12 scripts/manage.py demo --port 8010
```

Open **http://127.0.0.1:8010**. Keep the terminal running; press **Ctrl+C** to stop. The equivalent launchers are `scripts\setup.ps1`, `scripts\run-demo.ps1`, and `.cmd` versions. The direct Python commands work when PowerShell script execution is restricted. Python 3.12 is used in these examples; a different installed version ≥3.12 can be selected instead. See the [Windows guide](docs/windows.md) for prerequisites, firmware, Docker Desktop, and troubleshooting, or the [getting started guide](docs/getting-started.md) for dashboard use.

On **Linux/macOS**:

```bash
./scripts/setup.sh
PORT=8010 ./scripts/run-demo.sh
```

Choose a different `--port` if 8010 is busy (or use `PORT=8011` with the shell launcher). The portal needs no frontend build step or external CDN. API documentation is at `/docs`. Recreate `.venv` when moving the project between operating systems; a Linux virtual environment cannot be reused on Windows.

The simulator produces a reading every second. In the portal's admin view, switch among normal supply, a supply warning, rationing, protected reserve, a branch leak, sensor failure, and recovery. The three-sample leak check and five-sample forecast may take a few readings to settle after a change. All displayed history and daily consumption come from readings recorded by the backend.

The local demo binds only to the local machine and needs no API key. It does not send MQTT valve commands. The deployment configuration generates an API key for changes made through the portal or API.

## Included

| Component | Location | What it does |
| --- | --- | --- |
| Controller and API | `backend/` | Forecasts reserve depletion, detects branch leaks, issues expiring commands, records history and daily use |
| Resident/admin portal | `frontend/` | Live tank and quota indicators, flow history, leak alerts, hardware status, simulator controls |
| ESP32 firmware | `firmware/esp32/` | AJ-SR04M distance, two YF-S201 meters, receiver float stop, local source reserve protection, one transfer valve |
| Deployment | `compose.yaml`, `scripts/manage.py bootstrap` | FastAPI, Mosquitto 2.0, InfluxDB 2.7, Grafana 11.4 |
| Flight recorder | `grafana/dashboards/water-rationing.json` | Eight provisioned panels, refreshing every five seconds |
| Verification | `tests/`, `scripts/browser_tests.py`, `firmware/esp32/test_native.py` | Controller, API, persistence, portal, accessibility, and native firmware safety tests |

## Controller behavior

The protected source reserve is 10% of configured capacity: **0.25 L for the 2.5 L source**. The average of the last five pipe-inlet readings predicts minutes to reserve. The source depth is approximately 20 cm and still requires calibration. With a starting 30 cm probe standoff, calculated full/empty distances are 30/50 cm and the 10% reserve boundary is 48 cm.

| Tank condition, evaluated in order | Master valve duty |
| --- | --- |
| Below 10% reserve | 0% |
| Invalid ultrasonic reading | At most 30% |
| Level below 25%, or forecast below 60 minutes | `max(20, level_percent)`% |
| Forecast from 60 to below 120 minutes | 100%, warning |
| Otherwise | 100% |

A branch imbalance above `max(0.3 L/min, 15% of inlet flow)` for three consecutive readings limits the branch valve to 25%. The first two readings show `SUSPECTED_LEAK`. A balanced reading clears the leak state. Branch restriction never opens a valve beyond a stricter tank limit. Reserve protection sets both logical commands to zero. The physical rig has **one** valve: default transfer mode applies the smaller master/branch command, and the receiver float can stop it locally.

**Both meters straddle the same transfer pipe:** source → valve → meter 1 → monitored section/leak tap → meter 2 → receiver. The ultrasonic probe measures the source; the receiver has a binary full-level float rather than a second continuous level sensor. See the [architecture notes](docs/architecture.md) for assumptions. The original 60/120-minute forecast thresholds are retained; at real flow of at least 1 L/min, this small source will normally enter rationing well before the larger-system time thresholds.

## Deploy the full stack

On Windows, install and start **Docker Desktop in Linux containers mode**, then run in PowerShell:

```powershell
py -3.12 scripts/manage.py bootstrap
docker compose up --build -d
```

Linux/macOS can use `python3 scripts/manage.py bootstrap` or `./scripts/bootstrap.sh`, followed by the same Compose command. See [deployment instructions](docs/deployment.md) for credentials, Grafana, LAN access, and switching to physical telemetry. Docker manages images and named data volumes in its own storage. On Windows its Linux backend can use WSL 2 or another supported Docker Desktop backend; the project commands run in PowerShell.

## Connect hardware

Read the [hardware and commissioning guide](docs/hardware.md) before wiring and the [firmware guide](firmware/README.md) before flashing. Copy `firmware/esp32/include/config.example.h` to `config.h`, configure credentials and calibration, then use the firmware build script.

The installed sensor is labelled **AJ-SR04M**. Firmware supports its confirmed ordinary trigger/echo mode (R19 open for the documented version), using a 20 µs trigger, 120 ms sampling, and conservative project bounds of 30–300 cm. GPIOs are TRIG 26, ECHO 34, flow 27/32, float 33, valve relay 25, and unused relay channel 23. Both relay selectors default to HIGH trigger; LOW turns both outputs off. There is one installed valve and no pump output.

**Physical actuation ships disabled** (`WATER_HARDWARE_COMMISSIONED=0`). The two 9 V batteries cannot directly supply the 12 V / 1 A valve, and Robu explicitly excludes that valve from gravity-fed use. The listed resistor `R225229` is 150 Ω, not a 2 kΩ divider resistor. Complete the power, pressure, GPIO-interface, float-orientation, and calibration checks in the [parts and wiring guide](docs/hardware.md) before enabling it. The software demo remains available without physical hardware.

## Verify

In PowerShell after setup:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check backend tests
.\.venv\Scripts\python.exe scripts/browser_tests.py install
.\.venv\Scripts\python.exe scripts/browser_tests.py run
py -3.12 firmware/esp32/test_native.py
```

Browser checks require Node.js with npm; firmware safety tests require a C++ compiler. The browser runner starts and cleans up its own isolated demo. See the [Windows guide](docs/windows.md) for installation details and [verification notes](docs/verification.md) for Linux commands, recorded results, CI status, and hardware/deployment checks that require their target environment.

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
