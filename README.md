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

## Team Branches

- `main` - stable integration branch.
- `trijal` - Trijal's working branch.
- `hardik` - Hardik's working branch.
- `gayatri` - Gayatri's working branch.
- `prashant` - Prashant's working branch.

Each member should work on their own branch and open a pull request into `main`
when their changes are ready.
