# ESP32 firmware

The PlatformIO project is in `esp32/`. It uses the plan's JSN-SR04T sensor, two YF-S201 flow sensors, and one active-low relay on an ESP32 Dev Module. Read [the wiring and commissioning guide](../docs/hardware.md) before powering hardware.

## Configure and build

1. For a physical device, copy `esp32/include/config.example.h` to `esp32/include/config.h` (ignored by Git). For a build check, leave `config.h` absent: the example configuration compiles without credentials and keeps networking disabled.
2. Set Wi-Fi credentials, broker LAN address, and MQTT credentials. The repository bootstrap creates the device credentials in `.secrets/tank-01.env`: copy `MQTT_USERNAME`, `MQTT_PASSWORD`, `DEVICE_ID`, and `FLAT_ID` into the corresponding `WATER_*` values. Use a reachable LAN IP for `WATER_MQTT_HOST`, not a Docker service name. To accept a physical ESP32 on your LAN, set `MQTT_BIND_ADDRESS=0.0.0.0` in the root `.env` and restart the broker. Keep access restricted to the intended network.
3. Select `WATER_VALVE_ROLE_MASTER` or `WATER_VALVE_ROLE_FLAT` to match the single installed valve. Defaults are device `tank-01`, flat `101`, a 200L tank, 150cm usable depth, and 25cm probe standoff. Calibrate these dimensions and both pulse-per-litre values for the actual rig.
4. With PlatformIO installed, run from the repository root on Linux/macOS:

   ```bash
   bash firmware/esp32/build.sh
   bash firmware/esp32/build.sh --target upload
   cd firmware/esp32
   PLATFORMIO_CORE_DIR="$PWD/.platformio" pio device monitor
   ```

The pinned dependencies are [PlatformIO Core 6.1.18](https://pypi.org/project/platformio/6.1.18/), Espressif32 platform 6.9.0, PubSubClient 2.8, and ArduinoJson 6.21.5. A physical pull-up/interface must keep the relay inactive during boot; firmware starts with GPIO 25 HIGH.

The existing Bash wrapper keeps its Linux/macOS behavior. The portable `esp32/build.py` wrapper works on Windows, Linux, and macOS and keeps PlatformIO, temporary files, and dependency caches inside `firmware/esp32`. It looks for PlatformIO in the firmware `.venv`, the repository root `.venv`, the Python interpreter running the script, and then the installed `pio`/`platformio` command. It executes Python modules directly so moving the checkout does not depend on an old `pio` launcher path. All build/upload arguments pass through to `platformio run`.

### Windows setup, build and upload

Use a fresh Windows checkout and Python 3.12 (64-bit); Linux virtual environments and downloaded toolchains must be recreated on Windows. The commands below run in PowerShell from the repository root. A native Windows installation needs no Bash or WSL. [PlatformIO documents Python installation and Windows PATH setup here](https://docs.platformio.org/en/latest/faq/install-python.html).

Create the root virtual environment if the general Windows setup has not already created it, then install the pinned firmware tool:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install platformio==6.1.18

# Compile the example without credentials or an attached board.
.\.venv\Scripts\python.exe .\firmware\esp32\build.py
```

For real hardware, copy the example and edit `firmware\esp32\include\config.h` with the values described above before uploading:

```powershell
Copy-Item .\firmware\esp32\include\config.example.h .\firmware\esp32\include\config.h
.\firmware\esp32\build.ps1 --target upload --upload-port COM3
```

Replace `COM3` with the board's port in **Device Manager > Ports (COM & LPT)**; unplug/reconnect the board to identify it. Use a USB data cable. If Windows does not install the driver automatically, identify the USB-to-UART chip on your exact board and use that chip manufacturer's driver, such as CP210x, FTDI, or CH340/CH9102 as applicable. [Espressif's serial connection guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/establish-serial-connection.html) explains port identification and links the CP210x/FTDI drivers. Keep serial monitors closed during upload. If the board cannot enter download mode automatically, follow the board's BOOT/EN instructions.

The PowerShell build wrapper forwards arguments and returns the build/upload exit code. If local PowerShell policy blocks `.ps1` files, use the same Python entry point directly:

```powershell
.\.venv\Scripts\python.exe .\firmware\esp32\build.py --target upload --upload-port COM3
```

To list ports or monitor the firmware at 115200 baud with the same local PlatformIO directory:

```powershell
$env:PLATFORMIO_CORE_DIR = Join-Path (Get-Location).Path "firmware\esp32\.platformio"
.\.venv\Scripts\python.exe -m platformio device list
.\.venv\Scripts\python.exe -m platformio device monitor --port COM3 --baud 115200
```

Exit the monitor with Ctrl+C before another upload. Use the Windows PC's reachable LAN IP as the MQTT host on the ESP32; `localhost` refers to the ESP32 itself. Start the broker with its LAN binding enabled and allow its configured listener through Windows Firewall for the intended private network, as described in the main Windows guide.

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

The portable runner also works on Linux/macOS with GCC or Clang:

```bash
python3 firmware/esp32/test_native.py
python3 firmware/esp32/test_native.py --cxx clang++
```

On Windows, install **Build Tools for Visual Studio** with the **Desktop development with C++** workload, then open **Developer PowerShell for Visual Studio** so MSVC and the Windows SDK are available. [Microsoft documents the required compiler environment](https://learn.microsoft.com/en-us/cpp/build/building-on-the-command-line?view=msvc-170). From the repository root, run:

```powershell
.\firmware\esp32\test-native.ps1
# Equivalent when .ps1 execution is blocked:
.\.venv\Scripts\python.exe .\firmware\esp32\test_native.py
```

Alternatively, install MinGW-w64 GCC or Clang with its matching native Windows runtime and put its tools on PATH. Select the compiler explicitly when several are installed; compiler paths containing spaces work without extra shell quoting inside the value:

```powershell
.\firmware\esp32\test-native.ps1 --cxx g++
.\.venv\Scripts\python.exe .\firmware\esp32\test_native.py --cxx "C:\Program Files\LLVM\bin\clang++.exe"
```

`CXX` can also select a compiler executable (without extra compiler flags). The native runner creates `.build\control_logic_test.exe` on Windows and executes it. GCC/Clang compile in strict C++11 mode with warnings as errors; MSVC uses `/std:c++14`, its oldest supported C++ mode, with `/W4 /WX`. Native logic tests do not require PlatformIO, an ESP32, Wi-Fi credentials, or a running broker. An ESP32 cross-compiler cannot replace a host compiler for this suite.

It checks geometry, median outlier rejection, immediate reserve closure, fault caps, boot state, command expiry, duty-cycle phase, millisecond counter rollover, UTC parsing, and replay rejection. Software tests do not validate GPIO voltage, acoustic reflections, relay behavior, valve closure, or hydraulic response. Complete the physical checklist in the hardware guide before wet operation.
