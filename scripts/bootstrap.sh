#!/usr/bin/env bash
# Create local credentials without printing secret values.
set -euo pipefail
umask 077

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$PROJECT_DIR"
command -v python3 >/dev/null || { echo "Python 3 is required." >&2; exit 1; }
command -v docker >/dev/null || { echo "Docker is required." >&2; exit 1; }
docker compose version >/dev/null
docker info >/dev/null 2>&1 || { echo "Start Docker and ensure your account can use it." >&2; exit 1; }

mkdir -p .secrets
chmod 700 .secrets
trap 'rm -f -- "$PROJECT_DIR/.secrets/mosquitto.passwd.pending"' EXIT

python3 - <<'PY'
from pathlib import Path
import os
import secrets

path = Path('.env')
lines = path.read_text().splitlines() if path.exists() else Path('.env.example').read_text().splitlines()
secret_keys = {
    'API_KEY', 'MQTT_PASSWORD', 'MQTT_DEVICE_PASSWORD',
    'INFLUX_ADMIN_PASSWORD', 'INFLUX_TOKEN', 'GRAFANA_ADMIN_PASSWORD',
}
values = {}
for line in lines:
    if line.strip() and not line.lstrip().startswith('#') and '=' in line:
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
if values.get('MQTT_USERNAME', 'backend') != 'backend':
    raise SystemExit('MQTT_USERNAME must remain backend to match mosquitto/acl.')
for key in secret_keys:
    if not values.get(key):
        values[key] = secrets.token_hex(32)
    # Keep Compose interpolation and the password file unambiguous.
    if any(ch in values[key] for ch in '\r\n:$#\"\' \\'):
        raise SystemExit(f'{key} contains unsupported characters; use a long alphanumeric password.')
written = set()
updated = []
for line in lines:
    key = line.split('=', 1)[0].strip()
    if not line.lstrip().startswith('#') and key in secret_keys:
        if key not in written:
            updated.append(f'{key}={values[key]}')
            written.add(key)
    else:
        updated.append(line)
for key in sorted(secret_keys - written):
    updated.append(f'{key}={values[key]}')
path.write_text('\n'.join(updated) + '\n')
os.chmod(path, 0o600)

Path('.secrets/mosquitto.passwd.pending').write_text(
    f"backend:{values['MQTT_PASSWORD']}\ntank-01:{values['MQTT_DEVICE_PASSWORD']}\n"
)
device_path = Path('.secrets/tank-01.env')
device_values = {}
if device_path.exists():
    for line in device_path.read_text().splitlines():
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            device_values[key] = value
device_path.write_text(
    '# Copy these values into the ESP32 private configuration. Set your host LAN address.\n'
    f"MQTT_HOST={device_values.get('MQTT_HOST', 'YOUR_COMPUTER_LAN_IP')}\n"
    f"MQTT_PORT={values.get('MQTT_PORT', '1883')}\n"
    f"MQTT_USERNAME=tank-01\nMQTT_PASSWORD={values['MQTT_DEVICE_PASSWORD']}\n"
    'DEVICE_ID=tank-01\nFLAT_ID=101\n'
)
os.chmod('.secrets/tank-01.env', 0o600)
PY

# The broker's own utility generates its supported password hash format.
# Credentials enter via a private file, never through command-line arguments.
docker run --rm --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$PROJECT_DIR/.secrets,target=/work" \
  --entrypoint mosquitto_passwd eclipse-mosquitto:2.0 \
  -U /work/mosquitto.passwd.pending
mv -- .secrets/mosquitto.passwd.pending .secrets/mosquitto.passwd
# The containing host directory stays private; the container can read this
# individually mounted file as its non-root Mosquitto user.
chmod 644 .secrets/mosquitto.passwd
docker compose config --quiet
echo "Credentials saved in .env and .secrets/tank-01.env. Existing credentials were preserved."
echo "Start the stack with: docker compose up --build -d"
