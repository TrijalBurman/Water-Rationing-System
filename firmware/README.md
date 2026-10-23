# ESP32 firmware

The PlatformIO project is in `esp32/`, targeting a classic ESP32 Dev Module. The owned rig uses an **AJ-SR04M**, two Robu `43647` YF-S201 flow sensors, a `610733` P35 float, channel 1 of the `1121234` relay module, and one `31396` normally closed valve. The source is **2.5 L**, the receiver **1.5 L**, and source usable depth is approximately **20 cm**. Read [the parts, wiring, and commissioning guide](../docs/hardware.md) before powering hardware.

Physical actuation defaults to **disabled** (`WATER_HARDWARE_COMMISSIONED=0`). A two-9 V battery arrangement cannot directly power the 12 V / 1 A valve; the seller also excludes that valve from gravity-fed use. Complete the guide's power, pressure, signal-interface, float, and calibration checks before setting commissioning to 1. The default compiles for inspection and sensing setup without claiming that the hardware is ready.

## Configure and build

1. Copy `esp32/include/config.example.h` to `esp32/include/config.h` (ignored by Git).
2. Set Wi-Fi credentials, broker LAN address, and MQTT credentials. The repository bootstrap creates the device credentials in `.secrets/tank-01.env`: copy `MQTT_USERNAME`, `MQTT_PASSWORD`, `DEVICE_ID`, and `FLAT_ID` into the corresponding `WATER_*` values. Use a reachable LAN IP for `WATER_MQTT_HOST`, not a Docker service name. To accept a physical ESP32 on your LAN, set `MQTT_BIND_ADDRESS=0.0.0.0` in the root `.env` and restart the broker. Keep access restricted to the intended network.
3. Keep `WATER_VALVE_ROLE_TRANSFER` for this one source-to-receiver valve; it applies `min(master_valve_percent, flat_valve_percent)`. Defaults are device `tank-01`, flat `101`, source 2.5 L, receiver 1.5 L, approximate source usable depth 20 cm, and starting probe standoff 30 cm. These imply full/empty distances 30/50 cm and a 10% reserve boundary at 48 cm (0.25 L). Measure the actual geometry and calibrate both 450-pulses/L starting values. Keep `WATER_HARDWARE_COMMISSIONED=0` until all physical checks pass. Review [hardware_config.h](esp32/include/hardware_config.h) when reusing an older private `config.h`; fallback defaults are not hardware auto-detection.
4. With PlatformIO installed, run from the repository root on Linux/macOS:

   ```bash
   bash firmware/esp32/build.sh
   bash firmware/esp32/build.sh --target upload
   cd firmware/esp32
   PLATFORMIO_CORE_DIR="$PWD/.platformio" pio device monitor
   ```

The pinned dependencies are [PlatformIO Core 6.1.18](https://pypi.org/project/platformio/6.1.18/), Espressif32 platform 6.9.0, PubSubClient 2.8, and ArduinoJson 6.21.5. Default `WATER_RELAY_ACTIVE_HIGH=1` requires **both relay trigger selectors HIGH**. Firmware starts GPIO 25 and the unused GPIO 23 LOW/off; a qualified hardware interface/off bias must also keep both inactive before firmware runs and when ESP32 power is absent. The seller's 3.3 V trigger chart does not establish safe input current or absence of 5 V backfeed. The optional active-low setting requires matching LOW selectors and a correspondingly safe inactive interface.

The build wrapper keeps PlatformIO, temporary files, and dependency caches inside `firmware/esp32`. It uses `esp32/.venv/bin/python -m platformio` when a local installation exists, otherwise the installed `pio` command. Using the Python module also works after relocating this project directory. In this workspace a local PlatformIO installation was prepared; use `.venv/bin/python -m platformio device monitor` there if `pio` is not on your PATH.

For encrypted MQTT, configure the broker's TLS listener, set `WATER_MQTT_TLS=1`, change the port (normally 8883), and supply its CA certificate. Hostname/certificate validation stays enabled. The default plain MQTT setup is for a trusted lab LAN.

Serial monitoring at 115200 baud reports raw distance, float state, stop reason, relay command, and effective duty once per second even before Wi-Fi/NTP succeeds. This supports dry checks while commissioning remains disabled. A `nan` echo is unavailable data, not an empty tank.

## Runtime behavior

- GPIO 26 triggers the AJ-SR04M and GPIO 34 captures echo. The two flow inputs are GPIO 27/32. Float GPIO 33 uses `INPUT_PULLUP`; closed to GND means permit, open/full/disconnected means stop. GPIO 25 controls the installed valve relay; GPIO 23 holds the unused second channel inactive. There is no second valve or pump output.
- Use the identified AJ board's ordinary trigger/echo mode, documented as R19 open. Trigger duration is 20 µs, sample interval 120 ms, echo timeout 40 ms, and filtering uses five valid samples. The accepted 30–300 cm distance range is a conservative project envelope, not an identification or universal sensor specification. Verify the actual board's mode, supply, ECHO voltage, and TRIG threshold before GPIO connection.
- The receiver float stops transfer locally on an open circuit. Release requires **500 ms continuously closed contact and a new command issued more than two seconds after recovery (covering allowed clock skew)**. A queued command from before a stop or MQTT reconnect cannot reopen the valve. Configure `WATER_FLOAT_ROLE_SOURCE_LOW` only if deliberately moving the float to source-low protection; one float cannot measure both locations.
- The relay remains off while uncommissioned, before a trusted source-level median, without a valid clock/live command, or when the float gate stops transfer. A credible raw reading below 10% closes on that sample without waiting for the median. A sensor fault resets the median, retains the last trusted level, and caps an otherwise permitted command at 30%; reserve closure takes priority. Uncommissioned level/volume estimates are not calibrated measurements.
- Default transfer role applies the smaller master/flat command. Advanced master-only and flat-only roles remain available for explicitly different installations; they do not create additional actuators. A critical source command closes the installed valve in every role.
- Commands are time-proportioned over a stable 30-second period: 25% means 7.5 seconds energized and 22.5 seconds off. It is not measured hydraulic flow or proportional valve position. Incoming 1 Hz commands do not restart the period. Verify actual valve/relay duty suitability and closing behavior.
- Network connection work runs on another ESP32 core, leaving local protection active. A detected offline/reconnect state invalidates the current command; a new session needs a new valid command. Command expiry or 10 seconds without replacement also closes the output. NTP must synchronize before MQTT starts or telemetry is published. Only the latest measurement is sent after reconnection.

## MQTT contract

Telemetry is published once per second to `watertank/<device_id>/telemetry` with QoS 0 and `retain=false`. Existing fields are `device_id`, `flat_id`, `timestamp` (UTC), source `level_percent`/`volume_l`, pipe `flow_lpm`/`flow_out_lpm`, `ultrasonic_distance_cm`, `sensor_status`, and effective `valve_percent`. No echo is JSON `null`; other invalid distances are numeric with `sensor_status="fault"`. Uncommissioned frames also report a fault and `setup_required`; numeric level/volume fields must not be shown as calibrated source measurements.

The two-tank profile adds these fields, validated together by the backend:

| Field | Meaning |
| --- | --- |
| `hardware_profile` | `"two_tank_transfer"` |
| `level_sensor_model` | `"AJ-SR04M"` |
| `receiver_capacity_l` | Configured receiver capacity, 1.5 L; not a receiver volume measurement |
| `float_switch_role` | `"receiver_full"` by default, or `"source_low"` for the alternate physical placement |
| `float_switch_state` | `"permit"`, `"stop_or_disconnected"`, or `"recovering"` |
| `transfer_permitted` | Commissioning/float/clock gate is clear; does not prove a live command, valid source level, energized relay, or water flow |
| `local_stop_reason` | `"none"`, `"setup_required"`, `"float_stop"`, `"float_recovering"`, or `"clock_unsynced"` |
| `relay_energized` | Commanded relay-output state; there is no valve-position feedback |
| `requested_valve_percent` | Accepted command before local level/duty restrictions; invalidation clears it |

`valve_percent` reports effective duty; `relay_energized` reports whether the output is currently energized within that duty cycle. A true gate or output does not establish that a mechanical valve opened. Clock-unsynchronized hardware does not publish telemetry before NTP succeeds, even though that stop reason is part of the schema. See [API examples](../docs/api.md) for legacy compatibility and two-tank metadata.

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

The default transfer role applies `min(master_valve_percent, flat_valve_percent)`. Master-only and flat-only roles select their corresponding command. Commissioning, float, source reserve, clock, session freshness, and command expiry still constrain the one physical valve. A `CRITICAL` tank command closes it. Independent master and branch valves require additional installed actuators and an explicitly designed topology.

## Verification

Run the portable control-logic suite without ESP32 tooling:

```bash
bash firmware/esp32/test-native.sh
```

It checks geometry, median outlier rejection, immediate reserve closure, fault caps, boot state, command expiry, duty-cycle phase, millisecond counter rollover, UTC parsing, replay rejection, transfer command limits, float recovery, and rejection of commands from before recovery/reconnection. Software tests do not validate GPIO voltage, acoustic reflections, relay behavior, valve closure, or hydraulic response. Complete the physical checklist in the hardware guide before wet operation.
