# Wiring and Commissioning Guide for the JSN SR04T Demo

## Before connecting anything

Use only low-voltage DC supplies. Keep the 12 V supply unplugged while wiring. The ESP32 GPIO pins are 3.3 V only: a 5 V sensor output must always pass through a voltage divider before it reaches an ESP32 GPIO.

The valve must be a **12 V DC normally-closed, direct-acting water solenoid valve** with a specified minimum operating pressure of 0 bar / 0 MPa. A pilot-operated valve that needs 0.02 MPa or more may not open from an elevated demo tank because gravity pressure is too low.

## Parts and pins

| Item | ESP32 pin | Other parts required |
| --- | --- | --- |
| JSN-SR04T trigger | GPIO 26 | Direct jumper wire |
| JSN-SR04T Echo | GPIO 34 | One 1 kohm and one 2 kohm resistor divider |
| YF-S201 flow 1 (inflow) | GPIO 27 | One 1 kohm and one 2 kohm resistor divider |
| YF-S201 flow 2 (outflow) | GPIO 32 | One 1 kohm and one 2 kohm resistor divider |
| Valve relay input | GPIO 25 | IN1 on 5 V relay board |

GPIO 34 is input-only and is intentionally used for the JSN Echo signal.

## 1. Low-voltage 5 V wiring

Use a regulated 5 V, 2 A supply or a 12 V-to-5 V buck converter. It powers the ESP32, JSN-SR04T, flow sensor, and relay board. The ESP32 may remain connected to the laptop USB while programming, but do not also connect a second 5 V supply to its 5 V/VIN pin at the same time.

| From | To |
| --- | --- |
| 5 V supply positive | ESP32 5 V/VIN, JSN VCC, YF-S201 red, relay VCC |
| 5 V supply negative | ESP32 GND, JSN GND, YF-S201 black, relay GND |
| JSN TRIG | ESP32 GPIO 26 |
| Relay IN1 | ESP32 GPIO 25 |

For this first version, the refill pump is manual/separate: do not connect relay IN2 to an ESP32 pin. Leave pump hardware disconnected until the level, flow sensor, and valve are working.

## 2. JSN-SR04T Echo divider

The JSN board may emit a 5 V Echo pulse. Connect it exactly as follows; the junction is the only point connected to GPIO 34.

```text
JSN ECHO ---[ 1 kohm ]---+--- ESP32 GPIO 34
                          |
                       [ 2 kohm ]
                          |
                         GND
```

Do not connect JSN Echo straight to ESP32 GPIO 34.

## 3. YF-S201 flow-sensor dividers

Both YF-S201 sensors have red = 5 V, black = GND, yellow = pulse signal. Because they are powered at 5 V, their yellow pulse outputs must each use a 1k/2k resistor divider to step 5 V down to 3.3 V:

* **Flow 1 (Inflow / Source)**: Yellow -> [1 kohm] -> ESP32 GPIO 27, and [2 kohm] -> GND.
* **Flow 2 (Outflow / Delivery)**: Yellow -> [1 kohm] -> ESP32 GPIO 32, and [2 kohm] -> GND.

```text
YF-S201 yellow ---[ 1 kohm ]---+--- ESP32 GPIO (27 for Flow 1, 32 for Flow 2)
                                |
                             [ 2 kohm ]
                                |
                               GND
```

Install both sensors in the direction of their moulded flow arrows. Keep tubing full of water while testing, otherwise flow readings will be erratic.

## 4. Valve and 12 V wiring

Use a separate 12 V, 3 A DC adapter for valve and pump loads. The relay contacts switch the 12 V positive line; the ESP32 never supplies valve current.

```text
12 V positive --- 1 A fuse --- Relay 1 COM
Relay 1 NO ------------------ Solenoid valve positive
Solenoid valve negative ----- 12 V negative
```

Use the relay's **NO** terminal, not NC. With the relay unpowered, the normally-closed valve receives no power and remains closed. If your valve has a polarity-marked suppression diode, follow the markings. If it does not, place a 1N4007 diode across its terminals: diode stripe/cathode to valve positive, anode to valve negative.

Before connecting any water, briefly test the relay with the valve disconnected. At startup the relay should be off. When the system requests 100% flow, the relay should energize. If your relay works backwards, change `VALVE_RELAY_ACTIVE_LOW` in `config.h` from `true` to `false`.

## 5. Optional refill pump wiring

Keep this separate until the sensor, flow sensor, and valve work. The pump moves water from the lower collection container back to the elevated tank.

```text
12 V positive --- 1 A fuse --- Manual switch or Relay 2 COM
Relay 2 NO ------------------ Float switch --- Pump positive
Pump negative ------------------------------- 12 V negative
```

Set the float switch orientation so it opens the circuit when the lower collection tank becomes empty. Check this with a multimeter before powering the pump. Put a flyback diode across a brushed DC pump: stripe to positive, other end to negative.

## 6. Plumbing and dual-sensor mounting

```text
Upper transparent tank
  | JSN probe in lid, vertical, facing down
  | PVC stilling tube under probe, open at both ends
  v gravity outlet
YF-S201 flow sensor 1 (Inflow / Source, follow arrow)
  v
12 V normally-closed solenoid valve
  v
Pipeline distribution segment (monitored for bursts / leaks)
  v
YF-S201 flow sensor 2 (Outflow / Delivery, follow arrow)
  v
Consumer tap / Lower collection tank
  ^
Optional pump and return tube
```

1. Put the upper tank at least 0.5 m above the lower tank.
2. Mount the JSN waterproof probe vertically in the upper tank lid. Keep its electronic controller board outside the tank in a dry enclosure.
3. Leave at least 25 cm between probe and maximum water level. The sensor blind zone is about 20 cm.
4. Put an open-ended 40–50 mm PVC stilling tube under the probe. Drill small holes at the lower side so water inside it follows the tank level but surface ripples are damped.
5. Secure every hose with clamps. Test with a small amount of water first, with electronics raised well above potential leaks.

## 7. After physical wiring

1. Copy `firmware/esp32/include/config.example.h` to `firmware/esp32/include/config.h`.
2. In `config.h`, set Wi-Fi credentials, the laptop's LAN IPv4 address as `MQTT_HOST`, and the MQTT username/password stored in `.env`. The ESP32 and laptop must be on the same Wi-Fi network; do not use `localhost` as MQTT host.
3. With the tank empty, measure the distance from the probe face to the bottom/water surface and set `SENSOR_EMPTY_DISTANCE_CM`.
4. Fill to the maximum permitted water level while leaving at least 25 cm below the probe. Measure again and set `SENSOR_FULL_DISTANCE_CM`.
5. Set `TANK_CAPACITY_L` to the actual litres at that maximum level.
6. Install PlatformIO, connect ESP32 over USB, then build and upload from `firmware/esp32`: `pio run -t upload`.
7. Open serial monitor: `pio device monitor -b 115200`. Confirm the ESP32 connects to Wi-Fi/MQTT before operating water hardware.
8. Start with the valve disconnected from plumbing. Confirm the Grafana dashboard shows changing ultrasonic distance when a flat object moves under the probe.
9. Connect the valve to tubing, add a small amount of water, and check the flow sensor reading. Confirm that the valve closes when level drops below 10%.
10. Only after all these checks, connect and test the refill pump and its float-switch safety cut-off.

## Software already running

The Docker stack is running on this computer:

| Service | Address |
| --- | --- |
| Grafana dashboard | `http://localhost:3000` |
| FastAPI status | `http://localhost:8000/health` |
| InfluxDB | `http://localhost:8086` |
| MQTT broker | Laptop LAN IP, port `1883` |

Sign in to Grafana with username `admin`; its password is the `GRAFANA_ADMIN_PASSWORD` value in `.env`. To run another no-hardware demonstration, use `python3 tools/simulate.py` from the project root.
