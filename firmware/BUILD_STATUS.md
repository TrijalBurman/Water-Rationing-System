# Firmware verification

Verified on 2026-09-27 inside this project directory.

| Check | Result |
| --- | --- |
| Native C++ safety tests | Passed |
| Native tests with AddressSanitizer and UndefinedBehaviorSanitizer | Passed during implementation |
| ESP32 default example configuration, master role | Compiled and linked successfully |
| ESP32 temporary configuration, flat role with TLS and networking enabled | Compiled and linked successfully |
| Physical upload, electrical, acoustic, relay and water-flow tests | Not performed |

The default example image uses **369,313 bytes flash** and **26,056 bytes static RAM**. The TLS/flat verification image uses **915,493 bytes flash** and **48,084 bytes static RAM**. Dynamic Wi-Fi/TLS memory is additional and must be checked on the actual board.

Toolchain: local PlatformIO 6.1.18, Espressif32 platform 6.9.0, Arduino ESP32 2.0.17 (`framework-arduinoespressif32 3.20017.241212+sha.dcc1105b`), Xtensa 8.4.0+2021r2-patch5, PubSubClient 2.8, and ArduinoJson 6.21.5. The Python 3.14 host emits an upstream esptool 4.5.1 `SyntaxWarning` about a return inside a finally block; both image builds completed successfully.

The TLS build used temporary dummy credentials solely to compile and link that code path. It did not contact a device or broker, validate a certificate, or flash hardware. The temporary `include/config.h` was removed afterward; the final build uses the safe example configuration with networking disabled.

Reproduce from the repository root:

```bash
bash firmware/esp32/test-native.sh
bash firmware/esp32/build.sh
```

The native suite covers geometry, median filtering, immediate reserve closure, sensor fault limits, boot closure, command expiry, duty-cycle phase, millisecond counter rollover, UTC parsing, and stale/replayed command rejection. Follow [the hardware commissioning checklist](../docs/hardware.md) before connecting a water supply or relying on physical cutoff behavior.
