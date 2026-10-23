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
    'level_percent': 80, 'volume_l': 160,
    'flow_lpm': 1.0, 'flow_out_lpm': 1.0,
    'ultrasonic_distance_cm': 55, 'sensor_status': 'ok', 'valve_percent': 100,
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
