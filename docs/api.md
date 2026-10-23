# API examples

Interactive schemas are at `/docs`; OpenAPI is at `/openapi.json`. These examples use the local demo port. Add `X-API-Key` with the configured key when using the deployment stack. The portal's admin view can keep that key in browser session storage.

## Manual telemetry

Stop the simulator before posting to its device. A timestamp must be current and include a timezone. This example generates it at execution time:

```bash
.venv/bin/python - <<'PY'
import json
import urllib.request
from datetime import datetime, timezone

base = 'http://127.0.0.1:8000'
headers = {'Content-Type': 'application/json'}
# If configured: headers['X-API-Key'] = '<your API_KEY>'

def post(path, payload):
    request = urllib.request.Request(base + path, data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(request) as response:
        return json.load(response)

post('/api/demo', {'action': 'stop'})
result = post('/telemetry', {
    'device_id': 'tank-01', 'flat_id': '101',
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'level_percent': 80, 'volume_l': 2.0,
    'flow_lpm': 1.0, 'flow_out_lpm': 1.0,
    'ultrasonic_distance_cm': 34, 'sensor_status': 'ok', 'valve_percent': 100,
})
print(json.dumps(result, indent=2))
PY
```

The result is a `Decision` with independent `tank_mode`, `flat_status`, and master/branch duty percentages. `eta_minutes` can be null. No-echo readings use `ultrasonic_distance_cm: null` and `sensor_status: "fault"`; they must still include the other telemetry fields. Invalid echo distance normalizes status to fault even if the sender says `ok`.

## Simulator actions

```json
{"action": "start", "scenario": "normal"}
{"action": "scenario", "scenario": "leak"}
{"action": "stop"}
{"action": "reset"}
```

Send one object per `POST /api/demo` request. Available scenarios: `normal`, `warning`, `rationing`, `critical`, `leak`, `sensor_fault`, `recovery`. A scenario action starts generation if stopped. Reset stops generation, returns the scenario to normal, and deletes local history/usage for the default demo device.

## MQTT

| Topic | Publisher | Subscriber |
| --- | --- | --- |
| `watertank/tank-01/telemetry` | Device `tank-01` | Backend in live mode |
| `watertank/tank-01/command` | Backend in live mode | Device `tank-01` |

Telemetry uses the same schema as the HTTP endpoint. The command includes all decision fields plus `device_id`, `command_id`, `issued_at`, and `expires_at`. Timestamps use RFC3339 UTC. The broker ACL prevents `tank-01` from issuing commands or publishing readings for another device.

## Error responses

| HTTP status | Meaning |
| --- | --- |
| 401 | Missing or invalid API key on a write route |
| 403 | Simulator requested in live mode |
| 404 | No stored readings for the requested device |
| 409 | Duplicate/out-of-order timestamp, conflicting device identity, or simulator owns that stream |
| 422 | Invalid fields, stale/future timestamp, excessive volume, or missing scenario |
| 503 | `/health/ready`: a configured MQTT or Influx dependency is unavailable |

The portal's resident/admin switch controls visible tools. It is not a user-account system. Reads are public on the deployment's configured interface, and changes use the API key. Keep the supplied loopback bindings for a single-machine demo; add deployment-specific access control before wider exposure.

## Two-tank hardware telemetry

The actual rig has a **2.5 L source** and **1.5 L receiver**. `level_percent` and `volume_l` describe the source only. The receiver has a float cutoff, not a continuous volume or percentage sensor. The manual example above uses the supported legacy payload for API experiments. The new firmware publishes the following additional metadata together:

```json
{
  "hardware_profile": "two_tank_transfer",
  "level_sensor_model": "AJ-SR04M",
  "receiver_capacity_l": 1.5,
  "float_switch_role": "receiver_full",
  "float_switch_state": "stop_or_disconnected",
  "transfer_permitted": false,
  "local_stop_reason": "float_stop",
  "relay_energized": false,
  "requested_valve_percent": 0
}
```

Merge these fields with the base reading; this object alone is not complete telemetry. `float_switch_state` is `permit`, `recovering`, or `stop_or_disconnected`. An open float circuit cannot distinguish a full receiver from a broken wire. The alternate role `source_low` is for deliberately relocating the one float, leaving the receiver without a full cutoff.

`local_stop_reason` is `none`, `setup_required`, `float_stop`, `float_recovering`, or `clock_unsynced`. A clear commissioning/float/clock gate reports `transfer_permitted=true`, `local_stop_reason=none`, and `float_switch_state=permit`. This does not guarantee a valid level, live command, energized relay, or actual flow. With a blocked gate, the backend sets both logical command limits to zero and reports `TRANSFER_STOPPED`; a measured critical source reserve retains higher priority. `setup_required` hides uncalibrated source estimates and does not interpret placeholder zero as a measured empty tank.

`valve_percent` reports effective local duty, `requested_valve_percent` the most recently accepted request, and `relay_energized` the commanded electrical output. None confirms mechanical valve position. The one physical valve uses the smaller source/pipe limit. Every profile-specific metadata field above is required with `hardware_profile=two_tank_transfer`; legacy payloads remain supported. Latest, overview, history/CSV, and Influx retain the metadata. See [hardware wiring and commissioning](hardware.md) before enabling actuation.
