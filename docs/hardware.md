# Hardware connections, assembly, and commissioning

This is the connection guide for the **implemented firmware**, checked against [`main.cpp`](../firmware/esp32/src/main.cpp), [`control_logic.h`](../firmware/esp32/include/control_logic.h), and [`config.example.h`](../firmware/esp32/include/config.example.h). Use this guide for assembly where the earlier [`implementation_plan.md`](../implementation_plan.md) differs. GPIO numbers below are the ESP32's **GPIO labels**, not header positions or physical package pin numbers.

## What is implemented

The firmware targets an ESP32 Dev Module, a **JSN-SR04T in trigger/echo mode**, two YF-S201 pulse flow sensors, and **one** normally closed 12V solenoid driven by an active-low relay. The firmware selects whether this relay represents the tank master valve or one flat valve. It does not implement a pump cutoff or a second relay: the original plan does not assign pins or driver hardware for them.

The backend exposes separate master and flat commands. With the single relay specified here, only the configured role is physically actuated. To demonstrate independent leak isolation while the shared supply stays open, fit an explicitly designed second controller/channel and revise the wiring and firmware configuration first. Never connect two independently controlled valve coils to this one relay expecting separate behavior.

## Components and connections

### Parts for one controller

| Quantity | Part | Selection notes |
| --- | --- | --- |
| 1 | Classic ESP32 development board with GPIO 25, 26, 27, 32, and 34 exposed | Firmware target is `esp32dev`; ESP32-C3/S3 boards are not interchangeable with this pinout |
| 1 | JSN-SR04T module and its matching waterproof probe | Must support the firmware's trigger/echo mode; confirm the exact PCB revision |
| 2 | YF-S201 flow meters | Check voltage, pulse-output circuit, flow range, pressure, thread size, and water compatibility on the supplied parts |
| 1 | Active-low, 3.3V-compatible relay interface/module | Usually powered at 5V; must stay inactive during ESP32 reset and loss of ESP32 power |
| 1 | Normally closed, 12V DC solenoid water valve | Confirm pressure requirement, continuous duty, coil current, and DC relay-contact rating |
| 3 each | 1.0kΩ and 2.0kΩ resistors, 1%, at least 1/4W | Three separate 5V pulse dividers; see output-type caveat below |
| 1 | Flyback diode selected for the coil | The plan proposes 1N4007; check its current/thermal rating against the actual valve |
| 1 each | Regulated 5V supply and 12V DC supply, fuse and holder | Size from measured loads; keep mains wiring inside approved enclosed supplies |
| As needed | Terminal blocks, suitable wire, dry electronics enclosure, hose/fittings, manual shutoff, and controlled leak tap | Match plumbing direction, pressure, and materials; use a separate branch for the test leak |

### Terminal-by-terminal connection table

| Component terminal | Connect to | Notes |
| --- | --- | --- |
| ESP32 GND | Logic ground bus | Common with 5V supply negative, sensors, all divider lower resistors, and the relay control interface |
| JSN-SR04T VCC | Regulated 5V rail | Confirm the installed revision's supply requirements |
| JSN-SR04T GND | Logic ground bus | Keep the electronics PCB dry |
| JSN-SR04T TRIG | **GPIO 26** | Firmware sends a 10µs 3.3V pulse; verify that the installed module accepts 3.3V triggering |
| JSN-SR04T ECHO | Divider A input; divider A midpoint → **GPIO 34** | Input-only GPIO; never connect a 5V echo directly |
| YF-S201 #1 VCC, usually red | Regulated 5V rail | Verify wire labels against the supplied part, not colour alone |
| YF-S201 #1 GND, usually black | Logic ground bus | Upstream meter |
| YF-S201 #1 signal, usually yellow | Divider B input; divider B midpoint → **GPIO 27** | `flow_lpm`; firmware counts rising edges |
| YF-S201 #2 VCC, usually red | Regulated 5V rail | Same supply as meter #1 |
| YF-S201 #2 GND, usually black | Logic ground bus | Downstream meter |
| YF-S201 #2 signal, usually yellow | Divider C input; divider C midpoint → **GPIO 32** | `flow_out_lpm`; firmware counts rising edges |
| Relay VCC | Its rated supply, normally regulated 5V | `JD-VCC`/opto-isolation jumpers are module-specific; consult its schematic |
| Relay control GND | Logic ground bus for a non-isolated interface | Do not assume an optocoupler automatically makes a jumpered board isolated |
| Relay input IN1 | **GPIO 25** via a compatible interface | LOW = relay energized/water valve open; HIGH = relay inactive/water valve closed |
| Relay COM | Fused 12V positive | Fuse near supply |
| Relay NO | Solenoid positive | Contact is open when relay is de-energized; water valve therefore closes |
| Relay NC | Leave disconnected | Insulate the unused terminal |
| Solenoid negative | 12V negative | Coil return |
| Diode cathode, striped end | Solenoid positive, after relay NO | Mount directly across the coil terminals |
| Diode anode, unstriped end | Solenoid negative | Do not put the diode in series with the coil |

Use a regulated supply for the ESP32 board as specified by its manufacturer. For a genuine ESP32-DevKitC V4, Espressif specifies **one** board power source at a time: USB, the 5V header, or the 3V3 header. Do not feed its external 5V header while USB also supplies it. Other development boards need their own power-path documentation. The sensors/relay may use a separate 5V supply with a common logic ground while the ESP32 uses USB; do not join the two positive supply outputs. See [Espressif's board power instructions](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html#power-supply-options).

Never connect the 12V rail to an ESP32 5V/3V3 pin, and never power the relay coil or water-valve coil from a GPIO. The relay's dry COM/NO contacts switch the 12V circuit; they do not connect 12V to IN1/VCC. With separate isolated supplies, the 12V coil loop does not need a ground link to the logic just to operate mechanical contacts. A shared non-isolated 12V-to-5V converter already joins their grounds; route coil return current directly to the supply, away from sensor ground wiring. The plan's 5V/2A and 12V/3A figures are starting supply ratings, not proof that a particular valve/relay combination is compatible.

### Three independent voltage dividers

Build one divider for the echo and one for each flow sensor:

```text
5V signal ── R1: 1.0kΩ ──┬── ESP32 input
                         │
                      R2: 2.0kΩ
                         │
                        GND
```

With a 5.0V source, the node is nominally 3.33V. The three divider midpoints must remain separate: A to GPIO 34, B to GPIO 27, C to GPIO 32. Use 1% resistors and verify actual pulse highs/lows, supply tolerance, and output drive strength. A multimeter may show only a pulse's average voltage; use an oscilloscope or equivalent peak measurement to check amplitude. ESP32 inputs are not 5V-tolerant; the [ESP32 datasheet's DC limits](https://documentation.espressif.com/esp32_datasheet_en.html) specify a high input at least `0.75 × VDD` and at most `VDD + 0.3V`. Do not treat 3.6V as a normal operating target.

GPIO 34 has no internal pull-up/pull-down, and the firmware configures all three sensor inputs as `INPUT`, with no internal pull-ups. If a flow sensor uses an open-collector output, select its external pull-up and level conversion together. Adding an arbitrary weak pull-up ahead of a 3kΩ divider can pull the pulse high too low. An output that is documented to permit a 3.3V pull-up can instead use that pull-up directly into the GPIO, with no 5V divider, provided the module has no conflicting internal 5V pull-up. Verify the complete output circuit and waveform; do not assume all YF-S201 variants are electrically identical.

The relay must accept 3.3V logic without putting 5V onto GPIO 25. Verify its schematic and input current. Use a suitable level-shifting driver if it does not. Its hardware bias/interface must keep it inactive through reset, boot, disconnected ESP32 power, and programming. A pull-up to a **GPIO-safe** 3.3V supply is appropriate only when compatible with that relay/interface; never add a pull-up from GPIO 25 directly to 5V. Check the complete power sequence on the bench.

If the installed JSN-SR04T requires a trigger high above the ESP32's 3.3V output, use a suitable non-inverting 3.3V-to-5V logic interface on TRIG. The ECHO path still needs its own reduction to ESP32-safe levels.

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

## Plumbing order and relay role

The two flow sensors measure **the same outgoing branch at two points**. Here, "inflow" means flow entering the monitored pipe section, not refill water entering the tank. Install both sensor arrows toward the outlet and follow the meter supplier's orientation/straight-pipe requirements. Keep the pipe full and purge air before calibration.

For the default **master role** (`WATER_VALVE_ROLE_MASTER`):

```text
Tank outlet → manual shutoff → NC solenoid → Flow #1 → monitored pipe → Flow #2 → outlet
                                                       │
                                              controlled leak tap
```

This one valve controls the complete rig's supply and follows `master_valve_percent`. The backend can display a branch leak alert, but its separate `flat_valve_percent` will not actuate this master-role relay.

For a **flat role** demonstration (`WATER_VALVE_ROLE_FLAT`):

```text
Shared supply ──┬── other flats (separate takeoffs)
                └── manual shutoff → NC solenoid → Flow #1 → pipe → Flow #2 → flat outlet
                                                             │
                                                    controlled leak tap
```

The monitored branch's valve follows `flat_valve_percent`, so a sustained leak normally commands 25% duty, or less if tank restrictions require it. Place the valve **before** the leak tap so closing it stops supply to the leak. Every legitimate outlet inside the measured section must also be accounted for by the downstream meter; an unmetered tap between sensors looks like a leak. Keep tank-refill plumbing separate from this measured section. A real shared master valve plus an independently controlled flat valve requires another designed output/controller and integration; changing the role setting does not add a second channel.

## Probe mounting and tank calibration

- Use the **JSN-SR04T only**, in its supported trigger/echo mode. The plan refers to Mode 0 and an open R27 pad; PCB revisions differ, so check the exact board's mode-selection documentation before soldering or changing pads.
- The sealed probe/cable can tolerate water exposure according to the supplied part's rating. The electronics board requires a dry enclosure and protected cable entries; it is not made waterproof by having a sealed transducer.
- Mount the probe vertically above the water, with at least **25cm from its face to the highest water/overflow level** as the starting geometry. Actual V2/V3 blind zones and installation tolerances vary; increase clearance if the installed version requires it. Firmware validity bounds are 20–600cm, so a plausible reading alone does not prove an installation is outside its blind zone.
- The plan proposes a 40mm PVC stilling tube with an open lower end and 4–5mm equalization holes. **Validate the acoustic path before adopting that diameter.** A narrow tube, joints, condensation, or the riser can reflect the broad ultrasonic beam. Check reliable readings at full, intermediate, and empty levels with flowing water; enlarge/change the mounting if needed. Keep the tube vented and verify that its water level follows the tank without lag.
- The default geometry is a constant-cross-section **200L** tank with **150cm usable depth** and a **25cm standoff**. Full distance is 25cm; empty distance is 175cm. Firmware computes `level = clamp((150 - (distance - 25)) / 150 × 100)` and `volume = 200 × level / 100`. A horizontal cylinder or irregular tank needs a calibrated distance-to-volume curve; do not use the linear assumption for such a tank.
- Flow meters should be in series, upstream and downstream of the branch being monitored. A leak outlet for the demonstration belongs **between the meters**. A meter at tank refill and another at apartment consumption do not form this same monitored branch and cannot be compared directly for leak isolation.
- Start with 450 pulses/L for each meter, then measure a known collected volume independently for each sensor and update both calibration constants. Low flow, mounting direction, turbine lag, and pressure affect accuracy.

### Values to put in the firmware configuration

Copy [`config.example.h`](../firmware/esp32/include/config.example.h) to the ignored `firmware/esp32/include/config.h`, then set the following for the physical rig:

| Setting | How to determine it | Default |
| --- | --- | --- |
| `WATER_VALVE_ROLE` | Select `WATER_VALVE_ROLE_MASTER` or `WATER_VALVE_ROLE_FLAT` for the installed pipe/valve | Master |
| `WATER_PROBE_STANDOFF_CM` | Probe face to maximum usable/full water surface | 25cm; firmware requires at least 25cm |
| `WATER_TANK_USABLE_HEIGHT_CM` | Full surface to the defined empty/zero-usable-volume level | 150cm |
| `WATER_TANK_CAPACITY_L` | Actual volume between those usable full and empty levels | 200L |
| `WATER_FLOW_IN_PULSES_PER_LITRE` | Upstream pulse count divided by measured collected litres | 450 |
| `WATER_FLOW_OUT_PULSES_PER_LITRE` | Downstream pulse count divided by measured collected litres | 450 |

For tank calibration, measure full distance `D_full` and empty distance `D_empty` from the probe face: standoff = `D_full`; usable height = `D_empty − D_full`. The firmware requires `standoff + height ≤ 600cm`. Also set the backend's `TANK_CAPACITY_L` to the same usable capacity; otherwise its reserve/ETA calculations can disagree with the ESP32.

For each flow meter, collect a known volume with the leak tap closed. If counting pulses externally, use `K_new = pulse_count / collected_litres`. If using integrated reported flow, use `K_new = K_old × reported_litres / collected_litres`, where reported litres = `sum(flow_lpm × actual_interval_seconds / 60)`. The stock firmware publishes L/min rather than a cumulative pulse counter. Use several volumes and flow rates within the actual meter's supported range, repeat, and calibrate both meters separately. Rebuild and flash after changing constants. Check balanced flow over complete duty cycles as well as steady flow; low-flow quantization and valve transitions can affect the three-reading leak decision.

Set Wi-Fi, the broker's reachable LAN address, MQTT credentials/device identity, and NTP server as described in [`firmware/README.md`](../firmware/README.md). Start the backend in its live-hardware configuration so the simulator does not publish competing readings. Networking and a valid clock are needed to open the valve even after all physical wiring is correct.

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
7. **Flow:** run known volumes through each meter and calibrate. Establish balanced branch flow, then introduce a controlled leak between sensors. A difference greater than `max(0.3 L/min, 15% of upstream flow)` must persist for three consecutive readings: the backend reports two suspected readings, then confirmed leakage on the third. A flat-role relay applies up to 25% duty (less when tank restrictions require); a master-role relay follows the tank command. At the default 450 pulses/L and 1-second telemetry window, a one-pulse difference is about 0.133 L/min, so small-flow or transient comparisons need physical validation.
8. **Recovery:** restore balanced flow and adequate level, check updated commands and telemetry, and confirm recovery. Repeat loss of sensor, Wi-Fi, broker, backend, and power individually before unattended operation.

## Verification status and references

The native C++ safety tests were run during implementation and passed. They cover geometry, median filtering, reserve priority, sensor fault limiting, expiry, duty phase, timer rollover, UTC timestamps, and replay rejection. ESP32 build status is recorded in `firmware/BUILD_STATUS.md`. **No physical ESP32, electrical measurements, relay tests, acoustic tests, or wet hydraulic tests have been performed in this workspace.**

Primary hardware references checked for this guide:

- [Espressif ESP32 Series datasheet](https://documentation.espressif.com/esp32_datasheet_en.html): electrical input limits and GPIO restrictions. These apply to the classic ESP32 used by this firmware.
- [Espressif ESP32 GPIO guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/gpio.html): GPIO 34 is input-only and has no internal pull-up/down.
- [Espressif ESP32-DevKitC V4 user guide](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html): header labels and mutually exclusive board power options; check the actual carrier board if it differs.
- [Vishay 1N4001–1N4007 datasheet](https://www.vishay.com/docs/88503/1n4001.pdf): stripe denotes cathode; the stated 1A average rating has temperature and mounting conditions, so it is not automatic approval for an unspecified coil.

No exact manufacturer, PCB revision, relay schematic, valve part number, or supplier datasheet is recorded for the purchased JSN-SR04T/YF-S201/relay/solenoid. Their supply, trigger threshold, pulse-output circuit, blind zone, IP rating, and hydraulic/coil ratings therefore remain **variant-specific checks**, not verified specifications of the hardware in hand. The 25cm standoff and 450 pulses/L are repository defaults requiring commissioning.

Firmware API references: [PlatformIO Espressif32](https://docs.platformio.org/en/latest/platforms/espressif32.html), [PubSubClient API](https://pubsubclient.knolleary.net/api), and [ArduinoJson 6 deserialization](https://arduinojson.org/v6/api/json/deserializejson/).
