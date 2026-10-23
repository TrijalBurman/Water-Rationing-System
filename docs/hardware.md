# Hardware assembly and commissioning

## What is implemented

The firmware targets an ESP32 Dev Module, a **JSN-SR04T in trigger/echo mode**, two YF-S201 pulse flow sensors, and **one** normally closed 12V solenoid driven by an active-low relay. The firmware selects whether this relay represents the tank master valve or one flat valve. It does not implement a pump cutoff or a second relay: the original plan does not assign pins or driver hardware for them.

The backend exposes separate master and flat commands. With the single relay specified here, only the configured role is physically actuated. To demonstrate independent leak isolation while the shared supply stays open, fit an explicitly designed second controller/channel and revise the wiring and firmware configuration first. Never connect two independently controlled valve coils to this one relay expecting separate behavior.

## Components and connections

| Connection | ESP32 pin / destination | Notes |
| --- | --- | --- |
| JSN-SR04T TRIG | GPIO 26 | 10µs 3.3V output pulse |
| JSN-SR04T ECHO | Divider midpoint → GPIO 34 | Input-only pin; never connect a 5V echo directly |
| YF-S201 upstream signal | Divider midpoint → GPIO 27 | Interrupt pulse input |
| YF-S201 downstream signal | Divider midpoint → GPIO 32 | Interrupt pulse input |
| Relay input IN1 | GPIO 25 via a 3.3V-compatible interface | Active LOW opens the valve; HIGH closes |
| Sensor VCC / relay module supply | Regulated 5V rail | Verify module requirements and available current |
| Logic ground | ESP32, sensor, divider and driver ground | Common reference for the specified non-isolated wiring |
| Relay COM | Fused 12V positive | Fuse near supply |
| Relay NO | Solenoid positive | NO opens electrically when relay is de-energized |
| Solenoid negative | 12V negative | Coil return |

Use a regulated supply for the ESP32 board as specified by its manufacturer. Never connect the 12V rail to an ESP32 5V/3V3 pin. Keep the sensor/logic supply separate from the switched coil path. The plan's 5V/2A and 12V/3A figures are starting supply ratings, not proof that a particular valve/relay combination is compatible.

### Three independent voltage dividers

Build one divider for the echo and one for each flow sensor:

```text
5V signal ── R1: 1.0kΩ ──┬── ESP32 input
                         │
                      R2: 2.0kΩ
                         │
                        GND
```

With a 5.0V source, the node is nominally 3.33V. Use 1% resistors and verify the actual high voltage, supply tolerance, and sensor output type. GPIO 34 has no internal pull-up/pull-down. If a flow sensor uses an open-collector output, provide its required external pull-up before the divider; do not assume all YF-S201 variants have the same output circuit.

The relay must accept 3.3V logic without putting 5V onto GPIO 25. Verify its schematic and input current. Use a suitable level-shifting driver if it does not. Its hardware bias/interface must keep it inactive through reset, boot, disconnected ESP32 power, and programming. A pull-up to a **GPIO-safe** 3.3V supply is appropriate only when compatible with that relay/interface; never add a pull-up from GPIO 25 directly to 5V. Check the complete power sequence on the bench.

### Correct solenoid circuit

The original plan's ASCII diagram visually joins the switched positive wire to the negative rail. **Do not make that connection.** The coil and flyback diode are the two branches between the switched positive node and the negative rail; there is no wire shorting those nodes together.

```text
12V positive ── fuse ── relay COM
                          relay NO ── switched positive ── solenoid (+)
                                                          [   COIL   ]
12V negative ──────────────────────────────────────────── solenoid (−)

Flyback diode directly across the coil:
  cathode (striped end) → solenoid (+), switched positive
  anode                → solenoid (−), 12V negative
```

Use a normally closed water valve so de-energizing its coil closes the water path, and the relay's **NO** contact so de-energizing the relay cuts coil power. Confirm the valve's pressure range, orientation, continuous-duty rating, and suitability for 30-second cycling.

Choose the fuse from the measured coil current, any inrush, wire ampacity, and supply short-circuit capability; **1A is not a universal fuse value**. Likewise, confirm relay contacts have a suitable DC inductive-load rating. A 1N4007 is the plan's proposed flyback diode; verify current, reverse-voltage, energy, and repetitive-duty ratings for the selected coil. Observe valve closing time because a flyback diode slows current decay. Keep coil power wiring away from pulse inputs.

## Probe mounting and tank calibration

- Use the **JSN-SR04T only**, in its supported trigger/echo mode. The plan refers to Mode 0 and an open R27 pad; PCB revisions differ, so check the exact board's mode-selection documentation before soldering or changing pads.
- The sealed probe/cable can tolerate water exposure according to the supplied part's rating. The electronics board requires a dry enclosure and protected cable entries; it is not made waterproof by having a sealed transducer.
- Mount the probe vertically above the water, with at least **25cm from its face to the highest water/overflow level** as the starting geometry. Actual V2/V3 blind zones and installation tolerances vary; increase clearance if the installed version requires it. Firmware validity bounds are 20–600cm, so a plausible reading alone does not prove an installation is outside its blind zone.
- The plan proposes a 40mm PVC stilling tube with an open lower end and 4–5mm equalization holes. **Validate the acoustic path before adopting that diameter.** A narrow tube, joints, condensation, or the riser can reflect the broad ultrasonic beam. Check reliable readings at full, intermediate, and empty levels with flowing water; enlarge/change the mounting if needed. Keep the tube vented and verify that its water level follows the tank without lag.
- The default geometry is a constant-cross-section **200L** tank with **150cm usable depth** and a **25cm standoff**. Full distance is 25cm; empty distance is 175cm. Firmware computes `level = clamp((150 - (distance - 25)) / 150 × 100)` and `volume = 200 × level / 100`. A horizontal cylinder or irregular tank needs a calibrated distance-to-volume curve; do not use the linear assumption for such a tank.
- Flow meters should be in series, upstream and downstream of the branch being monitored. A leak outlet for the demonstration belongs **between the meters**. A meter at tank refill and another at apartment consumption do not form this same monitored branch and cannot be compared directly for leak isolation.
- Start with 450 pulses/L for each meter, then measure a known collected volume independently for each sensor and update both calibration constants. Low flow, mounting direction, turbine lag, and pressure affect accuracy.

## Local protection and operating limits

Firmware drives the relay inactive at startup and waits for a full valid median window, valid UTC time, and a fresh command before opening. It samples every 120ms and captures echo edges by interrupt. A credible raw level below 10% immediately closes the relay on that sample, without waiting for the five-sample median or a network round trip. This is the measured-level reserve safeguard; an invalid echo cannot establish the actual water level.

On an invalid echo, the firmware marks `sensor_status=fault`, starts a new median window, retains the last trusted level, and caps a live command at 30%. An existing reserve lock continues to close the valve, and a device that has never obtained a valid level stays closed. A broken level sensor therefore cannot provide reliable reserve measurements: the 30% cap is the plan's fallback, not proof that 10% reserve remains.

The duty window is 30 seconds. A 25% command means 7.5 seconds energized per window; it does not promise 25% hydraulic flow. An operator must establish that the relay/solenoid can tolerate the switching pattern without water hammer or overheating. Commands expire after their UTC expiry or a 10-second local timeout. Replayed commands and commands from before the current MQTT connection are rejected.

There is no wired pump-control output in this project. The backend's critical state can close the configured valve; it cannot stop an externally wired pump. Any pump needs separately engineered dry-run protection and a rated control interface.

## Benchtop checklist

Complete these checks with the actual hardware. The software test suite does not perform them.

1. **Power off:** inspect all connections, diode orientation, fuse rating, relay COM/NO selection, and absence of a switched-positive-to-ground short. With modules disconnected, confirm each divider is 3kΩ input-to-ground and 2kΩ node-to-ground. Connected electronics can change resistance measurements.
2. **Logic only:** measure the 5V and 3.3V rails and divider peak voltages. Verify no GPIO exceeds its board's limits. Confirm relay inactive with reset held, during flashing, and when ESP32 power is removed but relay supply remains on.
3. **Probe:** compare measured distances against a ruler at 25cm or the device's greater required minimum, intermediate positions, and tank-empty distance. Check no-echo and out-of-range faults. Repeat through the actual riser/stilling tube with condensation and turbulence representative of use.
4. **Valve power:** with fluid operation safe, apply a fresh command for the selected role and verify current, coil heating, energized flow, and power-loss closure. Some valves need water pressure to operate; do not assume audible clicking proves shutoff. Check 25%, 30%, and 100% duty timing.
5. **Reserve:** establish a level above reserve, then present a below-10% distance (greater than 160cm with default geometry). Verify immediate closure. Repeat with Wi-Fi disconnected and while broker connection attempts fail. Confirm a fault after a low-level reading cannot reopen the valve.
6. **Communication:** verify NTP synchronization, matching device/topic ACLs, and fresh telemetry. Stop backend commands and confirm closure within 10 seconds or the shorter command expiry. Reboot with a retained old command and verify it does not open. Test incorrect device ID, expired command, duplicate ID, and invalid percentage rejection.
7. **Flow:** run known volumes through each meter and calibrate. Establish balanced branch flow, then introduce a controlled leak between sensors. The backend should report two suspected samples, then confirmed leakage on the third sample. A flat-role relay should apply the 25% command; a master-role relay follows the tank command.
8. **Recovery:** restore balanced flow and adequate level, check updated commands and telemetry, and confirm recovery. Repeat loss of sensor, Wi-Fi, broker, backend, and power individually before unattended operation.

## Verification status and references

The native C++ safety tests were run during implementation and passed. They cover geometry, median filtering, reserve priority, sensor fault limiting, expiry, duty phase, timer rollover, UTC timestamps, and replay rejection. ESP32 build status is recorded in `firmware/BUILD_STATUS.md`. **No physical ESP32, electrical measurements, relay tests, acoustic tests, or wet hydraulic tests have been performed in this workspace.**

Firmware API references: [PlatformIO Espressif32](https://docs.platformio.org/en/latest/platforms/espressif32.html), [PubSubClient API](https://pubsubclient.knolleary.net/api), and [ArduinoJson 6 deserialization](https://arduinojson.org/v6/api/json/deserializejson/). Hardware variant ratings must come from the datasheets supplied with the actual purchased parts.
