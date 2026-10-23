# ESP32 firmware

The PlatformIO project is in `esp32/`, targeting a classic ESP32 Dev Module. The owned rig uses an **AJ-SR04M**, two Robu `43647` YF-S201 flow sensors, a `610733` P35 float, channel 1 of the `1121234` relay module, and one `31396` normally closed valve. The source is **2.5 L**, the receiver **1.5 L**, and source usable depth is approximately **20 cm**. Read [the parts, wiring, and commissioning guide](../docs/hardware.md) before powering hardware.

Physical actuation defaults to **disabled** (`WATER_HARDWARE_COMMISSIONED=0`). A two-9 V battery arrangement cannot directly power the 12 V / 1 A valve; the seller also excludes that valve from gravity-fed use. Complete the guide's power, pressure, signal-interface, float, and calibration checks before setting commissioning to 1. The default compiles for inspection and sensing setup without claiming that the hardware is ready.

## Configure and build

1. For a physical device, copy `esp32/include/config.example.h` to `esp32/include/config.h` (ignored by Git). For a build check, leave `config.h` absent: the example configuration compiles without credentials and keeps networking disabled.
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

The existing Bash wrapper keeps its Linux/macOS behavior. The portable `esp32/build.py` wrapper works on Windows, Linux, and macOS and keeps PlatformIO, temporary files, and dependency caches inside `firmware/esp32`. It looks for PlatformIO in the firmware `.venv`, the repository root `.venv`, the Python interpreter running the script, and then the installed `pio`/`platformio` command. It executes Python modules directly so moving the checkout does not depend on an old `pio` launcher path. All build/upload arguments pass through to `platformio run`.

### Windows setup, build and upload

Use a fresh Windows checkout and Python 3.12 (64-bit); Linux virtual environments and downloaded toolchains must be recreated on Windows. The commands below run in PowerShell from the repository root. A native Windows installation needs no Bash or WSL. [PlatformIO documents Python installation and Windows PATH setup here](https://docs.platformio.org/en/latest/faq/install-python.html).

Create a separate firmware environment and install the pinned tool there. PlatformIO requires different versions of some Python packages than the backend lockfile, so keep its dependencies in this dedicated environment:

```powershell
py -3.12 -m venv firmware/esp32/.venv
.\firmware\esp32\.venv\Scripts\python.exe -m pip install platformio==6.1.18

# Compile the example without credentials or an attached board.
py -3.12 .\firmware\esp32\build.py
```

For real hardware, copy the example and edit `firmware\esp32\include\config.h` with the values described above before uploading:

```powershell
Copy-Item .\firmware\esp32\include\config.example.h .\firmware\esp32\include\config.h
.\firmware\esp32\build.ps1 --target upload --upload-port COM3
```

Replace `COM3` with the board's port in **Device Manager > Ports (COM & LPT)**; unplug/reconnect the board to identify it. Use a USB data cable. If Windows does not install the driver automatically, identify the USB-to-UART chip on your exact board and use that chip manufacturer's driver, such as CP210x, FTDI, or CH340/CH9102 as applicable. [Espressif's serial connection guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/establish-serial-connection.html) explains port identification and links the CP210x/FTDI drivers. Keep serial monitors closed during upload. If the board cannot enter download mode automatically, follow the board's BOOT/EN instructions.

The PowerShell build wrapper forwards arguments and returns the build/upload exit code. If local PowerShell policy blocks `.ps1` files, use the same Python entry point directly:

```powershell
py -3.12 .\firmware\esp32\build.py --target upload --upload-port COM3
```

To list ports or monitor the firmware at 115200 baud with the same local PlatformIO directory:

```powershell
$env:PLATFORMIO_CORE_DIR = Join-Path (Get-Location).Path "firmware\esp32\.platformio"
.\firmware\esp32\.venv\Scripts\python.exe -m platformio device list
.\firmware\esp32\.venv\Scripts\python.exe -m platformio device monitor --port COM3 --baud 115200
```

Exit the monitor with Ctrl+C before another upload. Use the Windows PC's reachable LAN IP as the MQTT host on the ESP32; `localhost` refers to the ESP32 itself. Start the broker with its LAN binding enabled and allow its configured listener through Windows Firewall for the intended private network, as described in the main Windows guide.

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

The portable runner also works on Linux/macOS with GCC or Clang:

```bash
python3 firmware/esp32/test_native.py
python3 firmware/esp32/test_native.py --cxx clang++
```

On Windows, install **Build Tools for Visual Studio** with the **Desktop development with C++** workload, then open **Developer PowerShell for Visual Studio** so MSVC and the Windows SDK are available. [Microsoft documents the required compiler environment](https://learn.microsoft.com/en-us/cpp/build/building-on-the-command-line?view=msvc-170). From the repository root, run:

```powershell
.\firmware\esp32\test-native.ps1
# Equivalent when .ps1 execution is blocked:
py -3.12 .\firmware\esp32\test_native.py
```

Alternatively, install MinGW-w64 GCC or Clang with its matching native Windows runtime and put its tools on PATH. Select the compiler explicitly when several are installed; compiler paths containing spaces work without extra shell quoting inside the value:

```powershell
.\firmware\esp32\test-native.ps1 --cxx g++
py -3.12 .\firmware\esp32\test_native.py --cxx "C:\Program Files\LLVM\bin\clang++.exe"
```

`CXX` can also select a compiler executable (without extra compiler flags). The native runner creates `.build\control_logic_test.exe` on Windows and executes it. GCC/Clang compile in strict C++11 mode with warnings as errors; MSVC uses `/std:c++14`, its oldest supported C++ mode, with `/W4 /WX`. Native logic tests do not require PlatformIO, an ESP32, Wi-Fi credentials, or a running broker. An ESP32 cross-compiler cannot replace a host compiler for this suite.

It checks geometry, median outlier rejection, immediate reserve closure, fault caps, boot state, command expiry, duty-cycle phase, millisecond counter rollover, UTC parsing, replay rejection, transfer command limits, float recovery, and rejection of commands from before recovery/reconnection. Software tests do not validate GPIO voltage, acoustic reflections, relay behavior, valve closure, or hydraulic response. Complete the physical checklist in the hardware guide before wet operation.
