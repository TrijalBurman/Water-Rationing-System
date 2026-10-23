# Firmware verification

## Current two-tank hardware update — 23 October 2026

The actual configuration is AJ-SR04M trigger/echo, two YF-S201 meters, one P35 float, and one transfer valve on a two-channel relay. Source capacity is 2.5 L, receiver 1.5 L, source usable depth approximately 20 cm, and starting probe standoff 30 cm. The shipped example keeps `WATER_HARDWARE_COMMISSIONED=0`.

Local GCC native checks passed: float open/disconnection and stable-contact recovery, two-second clock-skew barriers, delayed/queued commands, MQTT session changes, millisecond rollover, one-valve source/pipe limits, 48 cm reserve boundary, reserve recovery median reset, duty timing, UTC parsing, and expiry/replay checks. Local ESP32 builds passed for the default inhibited example, a commissioned HIGH-trigger receiver-full profile, and a commissioned LOW-trigger/source-low profile with TLS. Compile-only configurations used dummy credentials and were removed afterward.

These native tests and all three ESP32 profiles also passed on both Windows and Linux in [GitHub Actions run 39992340503](https://github.com/TrijalBurman/Water-Rationing-System/actions/runs/39992340503), testing Windows code commit `72730c7`. The firmware sources are shared with `trijal`. Windows used MSVC for native tests; Linux used GCC. See [verification.md](../docs/verification.md) for application and integration results.

Serial output at 115200 baud now shows raw AJ distance, float circuit state, local gate reason, relay command, and effective duty once per second, even before networking/time synchronization. It does not print credentials. `nan` distance indicates no valid echo; it is not an empty-tank measurement.

**No physical upload, electrical/acoustic measurements, pressure tests, or wet tests have been performed.** The purchased 12 V / 1 A valve is not gravity-feed rated, and the supplied 9 V batteries do not provide its required supply. Build success does not commission those components.

## Historical implementation — 27 September 2026

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
