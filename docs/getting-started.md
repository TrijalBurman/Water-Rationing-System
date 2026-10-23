# Start WaterWise

## Start the dashboard on this computer

These steps run the dark dashboard, backend controller and simulated sensor readings. The local demo works without an ESP32 or Docker. The frontend is served by the backend, so you only need one running terminal.

### 1. Open a terminal in the project folder

On Windows, open **PowerShell** and change to your checkout, for example:

```powershell
Set-Location "D:\Final Year Project\Water-Rationing-System"
```

Use your actual folder. For a fresh Windows clone and prerequisites, follow the [Windows guide](windows.md). Commands support project paths with spaces.

On the original Linux computer:

```bash
cd /run/media/trijal/HDD/FinalYearProjectByAstra
```

The [drive path repair record](drive-path-repair.md) describes that Linux machine only; those mount-repair scripts are not Windows setup steps.

### 2. Install dependencies if needed

For the first run on a new machine, or if dependencies are missing, run:

```powershell
py -3.12 scripts/manage.py setup
```

On Linux/macOS:

```bash
bash scripts/setup.sh
```

Setup requires Python 3.12 or newer and internet access for downloads. The Windows examples select Python 3.12; select another installed version ≥3.12 if necessary. Setup creates the Python environment and caches inside this project folder. You do not need to activate the environment manually. Recreate the environment when moving between operating systems; do not copy a Linux `.venv` for use on Windows.

### 3. Start the project

```powershell
py -3.12 scripts/manage.py demo --port 8010
```

On Linux/macOS:

```bash
PORT=8010 bash scripts/run-demo.sh
```

Wait for the message that Uvicorn is running at `http://127.0.0.1:8010`. Keep this terminal open while using the dashboard.

### 4. Open the dashboard

Open [WaterWise](http://127.0.0.1:8010/frontend/) in a browser on this computer.

The simulator starts automatically. After a few seconds, you should see the tank level, flow readings, daily allowance and history chart. The readings are simulated; they are not measurements from physical sensors.

- **Overview:** tank level, allowance, flow chart and valve commands.
- **Activity & history:** recorded readings and CSV download.
- **System health:** sensor, connection and controller status. MQTT and InfluxDB are not configured in this local demo.
- **Admin / Operations:** try balanced supply, warning, rationing, protected reserve, leak, sensor fault and recovery scenarios. Allow a few readings for decisions to settle.

No login or API key is needed for the local demo. **Reset demo** clears the local demo readings and history.

### 5. Stop and restart

Press **Ctrl+C** in the server terminal to stop it. Closing only the browser tab does not stop the server.

For future runs, use just:

```powershell
py -3.12 scripts/manage.py demo --port 8010
```

Run from your checkout. On Linux/macOS, reuse `PORT=8010 bash scripts/run-demo.sh`. You do not need to rerun setup each time. Recorded data is kept in the project's `data/` directory. Use `--data-dir ".runtime\separate demo"` with the Python launcher to keep another demo's history separately.

## If it does not start

| What you see | What to do |
| --- | --- |
| Folder does not exist | Confirm your checkout's current drive/folder and quote paths containing spaces. The `/run/media/...` path applies only to the original Linux computer. |
| Missing Python environment or missing module | Run `py -3.12 scripts/manage.py setup` on Windows or `bash scripts/setup.sh` on Linux/macOS, then start again. |
| Address already in use | Try opening the dashboard: another copy may already be running. To use a different port, run `py -3.12 scripts/manage.py demo --port 8011` on Windows or `PORT=8011 bash scripts/run-demo.sh` on Linux/macOS, then open `http://127.0.0.1:8011/frontend/`. |
| PowerShell blocks a `.ps1` launcher | Use the direct Python commands above or the `.cmd` wrappers. |
| Browser cannot connect | Keep the server terminal open, check it for an error, and use the same port in the browser and launch command. |
| Readings have stopped | Open **Admin / Operations** and select **Start simulation** if the simulator is stopped. |

Useful local pages while the server is running:

- [Dashboard](http://127.0.0.1:8010/frontend/)
- [Backend health](http://127.0.0.1:8010/health)
- [Interactive API documentation](http://127.0.0.1:8010/docs)

## Run with physical sensors or Grafana

Use the [complete deployment guide](deployment.md) for MQTT, InfluxDB, Grafana and live ESP32 telemetry. That route requires Docker Compose and uses Docker-managed storage in addition to this project folder.

For the ESP32, follow the [hardware connection guide](hardware.md) and [firmware setup guide](../firmware/README.md). The deployment guide explains the live-mode settings, broker LAN address and device credentials. The local demo launcher above is for simulation and does not send MQTT valve commands.
