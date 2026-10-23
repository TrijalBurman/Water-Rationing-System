# Run WaterWise on Windows

The `windows` branch supports native Python, PowerShell, Command Prompt, ESP32 builds/uploads, browser checks, and Docker Desktop deployment. The local dashboard and simulator need **Python only**. The full stack uses Linux container images through Docker Desktop. Hardware wiring and control behavior are unchanged; use the [hardware connection guide](hardware.md).

## Install what you need

| Task | Required tools |
| --- | --- |
| Local dashboard, simulator, backend tests | 64-bit Python 3.12 or newer with pip and the `py` launcher; Git to clone |
| Complete MQTT/InfluxDB/Grafana deployment | Docker Desktop with a working Linux containers backend and Compose |
| Browser and accessibility checks | Node.js with npm; Chromium is downloaded by the browser installer |
| ESP32 compilation and upload | Python and PlatformIO installed as shown in the firmware guide; USB data cable and the driver for your board's USB bridge |
| Native C++ safety tests | A supported C++ compiler available to the terminal; see [firmware instructions](../firmware/README.md) |

Install Python using the [official Windows instructions](https://docs.python.org/3.12/using/windows.html). Examples below select Python 3.12 with `py -3.12`; choose another installed version ≥3.12 if necessary, for example `py -3.14`. Check `py -3.12 --version` before starting. If `py` is unavailable but the correct interpreter is on PATH, replace `py -3.12` with `python`.

For Docker Desktop, follow [Docker's current Windows requirements and installation guide](https://docs.docker.com/desktop/setup/install/windows-install/), enable its supported Linux backend, and wait until its engine is running. This project does not use Windows container images. Docker's WSL 2 backend can be used without opening a WSL shell to run any project command.

## Clone and start the dashboard

Run in an ordinary PowerShell terminal:

```powershell
git clone --branch windows https://github.com/TrijalBurman/Water-Rationing-System.git
Set-Location .\Water-Rationing-System
py -3.12 scripts/manage.py setup
py -3.12 scripts/manage.py demo --port 8010
```

Open [the dashboard](http://127.0.0.1:8010/frontend/). The terminal stays open while the server runs; stop it with **Ctrl+C**. For later runs, only the final command is needed. Choose another `--port` if 8010 is occupied.

Setup creates `.venv\Scripts\python.exe` and installs dependencies inside the project. No environment activation is required. The launcher runs the same FastAPI app and portal as the Linux version, binds to loopback, enables simulated readings, and leaves MQTT valve commands disabled. The dashboard uses local assets and needs no frontend build or Node.js for ordinary use.

The native wrappers provide the same entry points:

```powershell
.\scripts\setup.ps1
.\scripts\run-demo.ps1 --port 8010
```

In Command Prompt, use `scripts\setup.cmd` and `scripts\run-demo.cmd --port 8010`. If PowerShell blocks `.ps1` execution, use the direct Python commands above or `.cmd` wrappers; no execution-policy change is required.

The default demo data is stored in `data/`. To keep a separate run's history:

```powershell
py -3.12 scripts/manage.py demo --port 8011 --data-dir ".runtime\separate demo"
```

Project paths and the data-directory option support spaces. Quote paths supplied at the terminal, for example `Set-Location "D:\Final Year Project\Water-Rationing-System"`. Keep the checkout path reasonably short for deeply nested compiler/dependency files. If a dependency reports a Windows path-length error, see [Python's long-path guidance](https://docs.python.org/3.12/using/windows.html#removing-the-max-path-limitation).

## Move an existing Linux checkout to Windows

Prefer a fresh clone of the `windows` branch. The original baseline is available on [`trijal`](https://github.com/TrijalBurman/Water-Rationing-System/tree/trijal).

A Python virtual environment is specific to its operating system and location. Do not reuse the Linux `.venv`, `firmware/esp32/.venv`, or compiled firmware/tool caches on Windows. Preserve your source and required local configuration/data, rename or remove the old generated environment folders, and run setup/build again to create Windows versions. [Python documents virtual environments as disposable and non-portable](https://docs.python.org/3.12/library/venv.html).

The paths `/run/media/trijal/HDD/...` and the [drive-repair record](drive-path-repair.md) describe the original Linux computer. `scripts/fix-drive-path.sh` and `scripts/remove-hdd1-alias.sh` repair that Linux mount configuration only; they are not Windows setup steps. Windows uses its own drive letters and mount paths.

## Start the complete Docker stack

Start Docker Desktop and select **Linux containers**, then run from the project directory:

```powershell
docker version
docker info --format '{{.OSType}}'
py -3.12 scripts/manage.py bootstrap
docker compose up --build -d
docker compose ps
```

The Docker OS check must print `linux`; `docker version` must include a server section. Bootstrap uses Docker's Mosquitto utility to generate the password file. Docker must therefore be installed and running **before bootstrap**. The equivalent native wrappers are `.\scripts\bootstrap.ps1` and `scripts\bootstrap.cmd`.

Bootstrap generates `.env`, `.secrets\tank-01.env`, and `.secrets\mosquitto.passwd`; it preserves existing credentials on subsequent runs. Keep these secrets out of Git and retrieve passwords from them locally. First image downloads/builds take time. Follow the [deployment guide](deployment.md) for service credentials, persistent volumes, and live hardware.

| Service | Default address |
| --- | --- |
| Portal | <http://localhost:8000> |
| API documentation | <http://localhost:8000/docs> |
| Grafana | <http://localhost:3000/d/water-rationing> |
| InfluxDB | <http://localhost:8086> |
| MQTT broker | `localhost:1883` |

Useful PowerShell checks:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/health/ready
docker compose logs --tail=100 backend mosquitto influxdb grafana
docker compose down
```

`docker compose down` retains the named data volumes. Those volumes live in Docker Desktop storage, rather than the Git checkout. Moving to another computer requires migrating deployment data separately.

## Connect an ESP32 to this Windows computer

1. Follow the [hardware guide](hardware.md) and [firmware guide](../firmware/README.md) for wiring, configuration, build, and upload. USB ports appear as Windows COM ports, for example `COM5`; use the port actually assigned in Device Manager. A charging-only cable cannot upload firmware.
2. In `.env`, set `APP_MODE=live`, `DEMO_AUTOSTART=false`, and `MQTT_BIND_ADDRESS=0.0.0.0`. Run `docker compose up -d` to apply the changes.
3. Find the Windows computer's Wi-Fi/Ethernet IPv4 address with `ipconfig`. Put that **LAN address** in `WATER_MQTT_HOST`; `localhost`, a Docker service name, and a WSL virtual adapter address are not the ESP32's broker address.
4. Keep the ESP32 and computer on the same reachable trusted LAN. Use `.secrets\tank-01.env` for the device's MQTT username/password and identity. Keep the backend's credentials off the ESP32.
5. If Windows Firewall blocks the ESP32, allow inbound **TCP 1883** (or the selected `MQTT_PORT`) on the trusted **Private** network profile, scoped to the local subnet. Set the computer's network profile to Private only for a network you trust. Configure this through Windows Defender Firewall with Advanced Security; leave the portal, Grafana, and InfluxDB loopback-only unless you need to share them.
6. Ensure clock synchronization/NTP works on the ESP32. Its relay stays closed until valid sensor initialization, UTC time, and a fresh command are available.

The supplied relay is one channel: choose master or flat operation in firmware. Windows support adds no pump output or second valve channel. Physical valve closure, level/flow calibration, and hydraulic behavior still need the [commissioning checklist](hardware.md#benchtop-checklist).

## Run automated checks

After setup, in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check backend tests
.\.venv\Scripts\python.exe -m ruff format --check backend tests
.\.venv\Scripts\python.exe scripts/browser_tests.py install
.\.venv\Scripts\python.exe scripts/browser_tests.py run
py -3.12 firmware/esp32/test_native.py
```

The browser installer uses Node.js/npm and downloads Chromium. The browser runner starts an isolated demo, runs the existing smoke/accessibility checks, and stops the server afterward. The tests reset their isolated simulator history. See [verification notes](verification.md) for recorded results and current CI status, and the [firmware guide](../firmware/README.md) for compiler setup and ESP32 build/upload commands.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| `py` or Python is not found | Install Python with pip/launcher, reopen the terminal, and check the selected version. Use `python` only if it resolves to Python ≥3.12. |
| `.venv\Scripts\python.exe` is missing after copying from Linux | Rename the old `.venv` and run setup again on Windows. |
| PowerShell says script execution is disabled | Run `py -3.12 scripts/manage.py setup` / `demo`, or use `.cmd` wrappers. |
| Port is occupied | Select a different `--port`; match that port in the browser URL. |
| Docker cannot connect to its daemon | Start Docker Desktop, wait for engine startup, and check `docker version` again. |
| Docker reports a Windows/Linux image mismatch | Switch Docker Desktop to Linux containers. |
| Browser installation cannot find npm | Install Node.js with npm and reopen the terminal. Ordinary dashboard use does not require Node.js. |
| ESP32 connects to Wi-Fi but not MQTT | Check the computer's LAN IPv4 address, broker binding, Private-network firewall scope, port, and device credentials. |
| USB board has no COM port | Check the data cable, board power, Device Manager, and its USB bridge driver's manufacturer instructions. |
