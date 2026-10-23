# Run the complete stack

The stack includes the FastAPI portal and controller, an authenticated Mosquitto 2.0 broker, InfluxDB 2.7, and Grafana 11.4. Docker Compose and Python 3 are required on the host. All four published services bind to `127.0.0.1` by default.

From this project directory:

```bash
./scripts/bootstrap.sh
docker compose up --build -d
docker compose ps
```

Bootstrap creates random credentials in `.env` and `.secrets/tank-01.env`. It uses Mosquitto's password utility to create `.secrets/mosquitto.passwd`. It never prints passwords and preserves existing credentials on subsequent runs. These generated files are local secrets and must remain excluded from version control. Run bootstrap before starting Compose, because the broker password file must exist.

The initial image downloads and build can take several minutes. The backend starts after the broker and InfluxDB become healthy. By default the stack starts a demo scenario automatically; set `DEMO_AUTOSTART=false` in `.env` if you prefer to start it through the portal.

| Service | Local address | Credentials |
| --- | --- | --- |
| Resident and admin portal | <http://localhost:8000> | Resident views are readable. Enter `API_KEY` from local `.env` in the admin controls. |
| Interactive API reference | <http://localhost:8000/docs> | Use the API key for state-changing operations. |
| Grafana flight recorder | <http://localhost:3000/d/water-rationing> | `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` in `.env` |
| InfluxDB explorer | <http://localhost:8086> | `INFLUX_ADMIN_USER` / `INFLUX_ADMIN_PASSWORD` in `.env` |
| MQTT broker | `localhost:1883` | Separate `backend` and `tank-01` principals |

Open `.env` locally to retrieve the API key and dashboard credentials. Do not paste them into issue reports, logs, or screenshots.

## Service checks

```bash
curl --fail http://localhost:8000/health
curl --fail http://localhost:8000/health/ready
curl --fail http://localhost:8000/devices/tank-01/latest
docker compose logs --tail=100 backend mosquitto influxdb grafana
```

`GET /health` reports whether the application is running and includes integration states. `GET /health/ready` returns HTTP 503 when a configured dependency is unavailable. `GET /devices/{device_id}/latest` returns the most recent telemetry and decision after a device has sent data. `POST /telemetry` accepts validated telemetry; mutation routes require the configured API key. The complete route and payload reference is available at `/docs`.

If Grafana initially shows no data, let the demo produce a few samples, leave Source set to `demo`, and select `tank-01` in the Device selector. The dashboard refreshes every five seconds. Select Source `api` to inspect manually submitted telemetry. Confirm that the selected time range includes incoming telemetry and that `/health` reports an available InfluxDB connection.

## Live ESP32 operation

1. Set `APP_MODE=live` and `DEMO_AUTOSTART=false` in `.env`.
2. Set `MQTT_BIND_ADDRESS=0.0.0.0` to make the broker reachable on the computer's trusted LAN. Keep the portal, Grafana, and InfluxDB loopback bindings unless you deliberately need them on your LAN.
3. Use the generated `tank-01` MQTT username and password from `.secrets/tank-01.env` in the ESP32 private configuration. Set its MQTT host to the computer's LAN address and use the configured published `MQTT_PORT`.
4. Follow the [hardware guide](hardware.md) and [firmware guide](../firmware/README.md), including level shifting and the relay's safe boot state.
5. Apply the changed configuration with `docker compose up -d`.
6. In Grafana, select Source `hardware` and the device receiving live telemetry. Demo history remains available under Source `demo` without mixing with live readings.

The shipped broker uses authenticated, unencrypted MQTT for a trusted local network. For use across untrusted networks, configure a TLS listener and matching ESP32 trust configuration before exposing it.

### MQTT permissions

| Principal | Allowed topics |
| --- | --- |
| `backend` | Read and write application topics; read broker system topics |
| `tank-01` | Publish `watertank/tank-01/telemetry`; subscribe to `watertank/tank-01/command` |

Anonymous clients are rejected. Keep `MQTT_USERNAME=backend`; bootstrap verifies that it matches the broker ACL. Adding another device requires its own password entry and device-specific ACL. Do not put backend credentials on the ESP32.

## Time series and flight recorder

InfluxDB uses organization `waterwise`, bucket `water_telemetry`, and a 30-day retention period by default. Backend telemetry is stored in measurement `water_telemetry`, tagged by `device_id` and `flat_id`, at the device's telemetry timestamp. Numeric telemetry and controller fields share the same point; mode and health values are string fields. Unavailable ETA values are omitted.

The provisioned Flux datasource obtains its organization, bucket, and token from the container environment. The Source selector separates `demo`, `hardware`, and manual `api` telemetry. The Device selector discovers identifiers within the selected source. The eight panels show:

1. Tank level with the 10%, 25%, and 50% thresholds.
2. Stored volume with a 20 L protected reserve label for the default 200 L tank.
3. Supply and delivery flow through the monitored branch.
4. Measured flow differential, the dynamic leak threshold, and its 0.3 L/min minimum.
5. Current finite depletion ETA. An ETA from an older frame is excluded when the latest frame has no ETA.
6. Independent master and flat valve duty-cycle commands.
7. Overall mode, tank state, and branch state as separate timelines.
8. JSN-SR04T echo distance and sensor health, with faults shown in red.

For a different tank capacity, update `TANK_CAPACITY_L`, the firmware calibration, and the volume panel's reserve label and threshold (10% of capacity). Change dashboard files in `grafana/dashboards/`; Grafana reloads them automatically. Provisioning does not retain edits made in the Grafana UI.

## Moving the project directory

Bootstrap finds the project from its own location, and Compose resolves configuration mounts relative to `compose.yaml`. Moving or remounting the directory requires no path edits in these files. Run commands from the project's current location. If the stack was already running, stop it before moving the directory, then run `docker compose up --build -d` from the new location so bind mounts use the new paths.

On the same Docker host, the fixed Compose project name `waterwise` keeps the same named data volumes after a directory move. Those volumes live in Docker's storage and are not copied with the project folder.

## Persistence and maintenance

Docker named volumes retain controller state, broker persistence, InfluxDB data and configuration, and Grafana settings. `docker compose down` stops and removes the containers while preserving these volumes. Avoid `docker compose down -v` unless you intend to erase their data.

```bash
# Rebuild the backend after a code change.
docker compose up --build -d

# Stop services while keeping stored data.
docker compose down
```

InfluxDB setup credentials and retention settings apply when its volume is first initialized. Changing them in `.env` does not update an existing database. Update existing users, tokens, or bucket retention through InfluxDB, then update the matching `.env` values and recreate dependent containers. Grafana's initial admin password also applies only on first initialization; change an existing password in Grafana itself.

To rotate MQTT credentials, update the corresponding `.env` values, rerun bootstrap, and restart the broker and backend. Copy the new device password into the firmware configuration and upload it. The bootstrap rerun preserves a LAN host already entered in `.secrets/tank-01.env`.

The local SQLite store and InfluxDB serve different purposes: SQLite keeps the portal's current state and quota history across restarts, while InfluxDB supplies the operations recorder. Back up the corresponding Docker volumes before moving or replacing a deployment.
