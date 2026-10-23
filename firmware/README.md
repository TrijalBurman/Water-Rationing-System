# ESP32 firmware

The PlatformIO project is in `esp32/`. It uses the plan's JSN-SR04T sensor, two YF-S201 flow sensors, and one active-low relay on an ESP32 Dev Module. Read [the wiring and commissioning guide](../docs/hardware.md) before powering hardware.

## Configure and build

1. Copy `esp32/include/config.example.h` to `esp32/include/config.h` (ignored by Git).
2. Set Wi-Fi credentials, broker LAN address, and MQTT credentials. The repository bootstrap creates the device credentials in `.secrets/tank-01.env`: copy `MQTT_USERNAME`, `MQTT_PASSWORD`, `DEVICE_ID`, and `FLAT_ID` into the corresponding `WATER_*` values. Use a reachable LAN IP for `WATER_MQTT_HOST`, not a Docker service name. To accept a physical ESP32 on your LAN, set `MQTT_BIND_ADDRESS=0.0.0.0` in the root `.env` and restart the broker. Keep access restricted to the intended network.
3. Select `WATER_VALVE_ROLE_MASTER` or `WATER_VALVE_ROLE_FLAT` to match the single installed valve. Defaults are device `tank-01`, flat `101`, a 200L tank, 150cm usable depth, and 25cm probe standoff. Calibrate these dimensions and both pulse-per-litre values for the actual rig.
4. With PlatformIO installed, run from the project directory:

   ```bash
   bash firmware/esp32/build.sh
   bash firmware/esp32/build.sh --target upload
   cd firmware/esp32
   PLATFORMIO_CORE_DIR="$PWD/.platformio" pio device monitor
   ```

The pinned dependencies are Espressif32 platform 6.9.0, PubSubClient 2.8, and ArduinoJson 6.21.5. The example configuration compiles without secrets and leaves networking disabled. A physical pull-up/interface must keep the relay inactive during boot; firmware starts with GPIO 25 HIGH.

The build wrapper keeps PlatformIO, temporary files, and dependency caches inside `firmware/esp32`. It uses `esp32/.venv/bin/python -m platformio` when a local installation exists, otherwise the installed `pio` command. Using the Python module also works after relocating this project directory. In this workspace a local PlatformIO installation was prepared; use `.venv/bin/python -m platformio device monitor` there if `pio` is not on your PATH.

For encrypted MQTT, configure the broker's TLS listener, set `WATER_MQTT_TLS=1`, change the port (normally 8883), and supply its CA certificate. Hostname/certificate validation stays enabled. The default plain MQTT setup is for a trusted lab LAN.

## Runtime behavior

- Trigger/echo: GPIO 26/34; flow in/out: GPIO 27/32; relay: GPIO 25. There is no second relay or pump-control pin.
- Echo edges and flow pulses use interrupts. Echoes are sampled every 120ms with a 40ms timeout and median of five valid samples; no long blocking echo waits occur in the control loop.
- The relay closes on the first valid raw reading below 10%, even when its median is still higher. It remains closed before the first good median. A sensor fault resets the median window, keeps the last trusted level, and caps an otherwise valid command at 30%; the reserve lock still wins.
- Commands are time-proportioned over a stable 30-second period. For example, 25% opens for 7.5 seconds and closes for 22.5 seconds. This is a duty percentage, not a measured flow percentage or proportional valve position. Incoming 1Hz commands do not restart the period.
- Network connection work runs on a separate ESP32 core. Local sensing and reserve closure continue through DNS, Wi-Fi, TLS, and MQTT outages. A command expires at its stated UTC expiry or after 10 seconds without a replacement, whichever is earlier. A connection loss therefore closes the valve within that bound; reserve shutdown remains immediate when sampled.
- NTP must synchronize before MQTT starts or telemetry is published. Until then, the valve stays closed. There is no buffer of historical telemetry: only the latest measurement is sent after reconnection.

## MQTT contract

Telemetry is published once per second to `watertank/<device_id>/telemetry` with QoS 0 and `retain=false`. The JSON fields are `device_id`, `flat_id`, `timestamp` (UTC), `level_percent`, `volume_l`, `flow_lpm`, `flow_out_lpm`, `ultrasonic_distance_cm`, `sensor_status`, and `valve_percent`. No echo is JSON `null`; other invalid distances are reported numerically with `sensor_status="fault"`. `valve_percent` is the effective locally limited duty command.

Commands arrive on `watertank/<device_id>/command` (QoS 1 subscription):

```json
{
  "device_id": "tank-01",
  "command_id": "unique-per-decision",
  "issued_at": "2026-09-26T12:00:00.123Z",
  "expires_at": "2026-09-26T12:00:10.123Z",
  "mode": "NORMAL",
  "tank_mode": "NORMAL",
  "flat_status": "NORMAL",
  "master_valve_percent": 100,
  "flat_valve_percent": 100
}
```

This is an illustrative expired command; it cannot actuate hardware. The backend must send fresh, non-retained commands. The firmware rejects wrong topic/device IDs, missing command fields, invalid percentages, non-UTC dates, expired/future commands, TTLs over 30 seconds, repeated IDs, non-increasing issue times, and commands issued before the current MQTT connection. These checks also reject stale retained messages even though PubSubClient does not expose the retained flag to its callback. UTC `Z` and `+00:00` formats, including fractional seconds, are supported. Backend and device clocks must be synchronized.

The master role applies `master_valve_percent`; the flat role applies `flat_valve_percent`. Local reserve protection and a `CRITICAL` tank command override either role. Demonstrating simultaneous independent tank and flat actuation needs another explicitly designed controller/relay channel; this implementation does not invent wiring for it.

## Verification

Run the portable control-logic suite without ESP32 tooling:

```bash
bash firmware/esp32/test-native.sh
```

It checks geometry, median outlier rejection, immediate reserve closure, fault caps, boot state, command expiry, duty-cycle phase, millisecond counter rollover, UTC parsing, and replay rejection. Software tests do not validate GPIO voltage, acoustic reflections, relay behavior, valve closure, or hydraulic response. Complete the physical checklist in the hardware guide before wet operation.
