# Water Rationing System

An IoT-based water management system that monitors tank level and flow rate,
predicts water depletion, detects anomalies, and triggers automated rationing
through a solenoid valve.

## Core Modules

- `backend/` - FastAPI service for ingestion, forecasting, alerts, and MQTT commands.
- `firmware/` - ESP32 code for ultrasonic sensor, flow sensor, and solenoid control.
- `infra/` - Docker, deployment, and cloud infrastructure files.
- `grafana/` - Dashboard provisioning and visualization assets.
- `docs/` - Project plan, architecture notes, demo script, and report material.

## Local Development

Start the full local stack:

```bash
docker compose up --build
```

Services:

- FastAPI: http://localhost:8000
- API docs: http://localhost:8000/docs
- Grafana: http://localhost:3000
- InfluxDB: http://localhost:8086
- MQTT broker: `localhost:1883`

Grafana login:

- Username: `admin`
- Password: `admin`

Publish simulated telemetry:

```bash
cd backend
pip install -r requirements.txt
python -m app.simulator --scenario normal
python -m app.simulator --scenario shortage
python -m app.simulator --scenario leak
```

Or from the repository root on Windows:

```powershell
.\scripts\demo.ps1 -Scenario shortage -Seconds 30
```

Use `normal` for baseline operation, `shortage` to reduce tank level quickly, and
`leak` to create a flow difference between upstream and downstream sensors. The
PowerShell helper publishes a compact historical sample window so Grafana's
default "Last 30 minutes" range shows the demo clearly.

## Team Branches

- `main` - stable integration branch.
- `trijal` - Trijal's working branch.
- `hardik` - Hardik's working branch.
- `gayatri` - Gayatri's working branch.
- `prashant` - Prashant's working branch.

Each member should work on their own branch and open a pull request into `main`
when their changes are ready.

See `docs/TEAM_WORKFLOW.md` for daily start, stop, push, and pull request steps.
