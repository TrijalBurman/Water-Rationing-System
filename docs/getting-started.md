# Start WaterWise

## Start the dashboard on this computer

These steps run the dark dashboard, backend controller and simulated sensor readings. The local demo works without an ESP32 or Docker. The frontend is served by the backend, so you only need one running terminal.

### 1. Open a terminal in the project folder

```bash
cd /run/media/trijal/HDD/FinalYearProjectByAstra
```

The external drive is configured to mount at `HDD` when accessed. See the [drive path repair record](drive-path-repair.md).

### 2. Install dependencies if needed

The project environment has already been prepared on this computer. For the first run on a new machine, or if dependencies are missing, run:

```bash
bash scripts/setup.sh
```

Setup requires Python 3.12 or newer and internet access for downloads. It creates the Python environment and caches inside this project folder. You do not need to activate the environment manually.

### 3. Start the project

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

```bash
cd /run/media/trijal/HDD/FinalYearProjectByAstra
PORT=8010 bash scripts/run-demo.sh
```

You do not need to rerun setup each time. Recorded data is kept in the project's `data/` directory.

## If it does not start

| What you see | What to do |
| --- | --- |
| Folder does not exist | Connect the external drive and confirm the project is available at the `HDD` path above. |
| Missing Python environment or missing module | Run `bash scripts/setup.sh` from the project folder, then start again. |
| Address already in use | Try opening the dashboard: another copy may already be running. To use a different port, run `PORT=8011 bash scripts/run-demo.sh` and open `http://127.0.0.1:8011/frontend/`. |
| Browser cannot connect | Keep the server terminal open, check it for an error, and use the same port in the browser and launch command. |
| Readings have stopped | Open **Admin / Operations** and select **Start simulation** if the simulator is stopped. |

Useful local pages while the server is running:

- [Dashboard](http://127.0.0.1:8010/frontend/)
- [Backend health](http://127.0.0.1:8010/health)
- [Interactive API documentation](http://127.0.0.1:8010/docs)

## Run with physical sensors or Grafana

Use the [complete deployment guide](deployment.md) for MQTT, InfluxDB, Grafana and live ESP32 telemetry. That route requires Docker Compose and uses Docker-managed storage in addition to this project folder.

For the ESP32, follow the [hardware connection guide](hardware.md) and [firmware setup guide](../firmware/README.md). The deployment guide explains the live-mode settings, broker LAN address and device credentials. The local demo launcher above is for simulation and does not send MQTT valve commands.
