# JSN SR04T Hardware and Calibration

## Sensor choice and limits

The prototype uses a JSN-SR04T V3.0 waterproof ultrasonic sensor. The probe is mounted at the tank top and measures the air gap to the water surface. Its practical range is about 20 to 600 cm. The sensor cannot read the first 20 cm beneath the probe, so leave at least 25 cm between the probe and the highest water level.

The sealed probe tolerates splash and humidity, but its controller board is not waterproof. Mount the board outside the tank in a dry enclosure. Foam, heavy condensation on the probe face, and severe surface turbulence can still affect ultrasonic readings. Use a vertical stilling tube to make the water surface calmer.

## ESP32 sensor connection

| JSN-SR04T pin | Connect to | Requirement |
| --- | --- | --- |
| VCC | ESP32 5 V/VIN pin or regulated 5 V rail | Do not use ESP32 3.3 V pin to power it. |
| GND | ESP32 GND | Common ground is required. |
| TRIG | ESP32 GPIO 26 | Direct connection. |
| ECHO | ESP32 GPIO 34 through a voltage divider | Never connect the possible 5 V Echo signal directly to ESP32. |

Build the Echo divider like this:

```text
JSN ECHO --- 1 kohm ---+--- ESP32 GPIO 34
                        |
                      2 kohm
                        |
                       GND
```

This converts an approximately 5 V Echo pulse to about 3.3 V. GPIO 34 is input-only, which is correct for Echo.

## Other electrical connections

| Part | ESP32 connection | Power / safety connection |
| --- | --- | --- |
| YF-S201 flow sensor 1 (Inflow / Source) | Signal to GPIO 27 interrupt input | Power at 5 V; reduce its 5 V pulse to 3.3 V with a 1 kohm/2 kohm divider. GND common with ESP32. |
| YF-S201 flow sensor 2 (Outflow / Delivery) | Signal to GPIO 32 interrupt input | Power at 5 V; reduce its 5 V pulse to 3.3 V with a second 1 kohm/2 kohm divider. GND common with ESP32. |
| 12 V normally-closed solenoid valve | GPIO 25 to relay IN1 | Valve is powered only through relay COM/NO contacts and 12 V supply; it must never be powered by ESP32. |
| Relay board | 5 V and GND from 5 V rail; IN1 from GPIO 25 | Use an opto-isolated board. The firmware defaults to active-low relay boards; change `VALVE_RELAY_ACTIVE_LOW` if yours is active-high. |
| Mini pump, optional refill | Relay IN2 or manual 12 V switch | Use a separate relay/MOSFET, flyback protection, fuse, and a float switch in series. Keep it off during initial valve testing. |

## Tank installation and calibration

1. Drill a hole in the tank lid and mount the JSN probe vertically downward. Seal around the cable, but do not seal the sensor controller board inside the tank.
2. Place an open-ended PVC stilling tube beneath the probe; it should reach into the water without touching the bottom. Drill small lower-side holes so the water inside the tube follows the tank level.
3. With the tank empty, measure the probe-to-water-bottom distance in cm. Set it as `SENSOR_EMPTY_DISTANCE_CM` in `config.h`.
4. Fill the tank to the highest permitted level, leaving at least 25 cm of air gap. Measure probe-to-water distance and set it as `SENSOR_FULL_DISTANCE_CM`.
5. Set `TANK_CAPACITY_L` to the amount of water at that full permitted level, then upload the firmware.
6. Check readings at empty, 25%, 50%, 75%, and full. Use the measured level, not the printed tank capacity, as the calibration reference.

## Fault and safety behaviour

- A distance below 20 cm, above 600 cm, no Echo pulse, or a reading beyond the calibrated empty distance is a sensor fault. The ESP32 reports it and holds water flow to a conservative maximum of 30%.
- If level falls below `MIN_SAFE_PERCENT`, the ESP32 commands the normally-closed valve shut even when Wi-Fi, MQTT, or the backend is unavailable.
- If upstream flow exceeds downstream flow by more than 0.3 L/min (or 15%) across 3 consecutive cycles, a pipeline leak is flagged: the valve is throttled to 25% locally on the ESP32 and centrally by FastAPI to curb leakage while preserving emergency flow.
- A float switch hard-wired in the pump circuit remains the final protection against dry-running the refill pump.
