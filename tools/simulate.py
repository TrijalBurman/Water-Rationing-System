"""Send a representative depletion/refill sequence to a running API."""
from datetime import datetime, timezone
import json
from time import sleep
from urllib.request import Request, urlopen

API_URL = "http://localhost:8000/telemetry"
DEVICE = "tank-01"
FLAT = "flat-101"

READINGS = [
    # (level_pct, volume_l, flow_in, flow_out, dist_cm, label)
    (82, 164, 0.7, 0.68, 31.3, "Normal operation (balanced dual flow)"),
    (55, 110, 1.1, 1.08, 41.5, "Warning operation (depletion ETA < 120m)"),
    (28, 56, 1.4, 1.38, 50.2, "Rationing operation (depletion ETA < 60m)"),
    # Leak injection sequence: Inflow >> Outflow on Flat 101 branch
    (26, 52, 2.2, 0.50, 51.0, "Pipe fracture: Sample 1 (suspected leak, debouncing)"),
    (25, 50, 2.2, 0.50, 51.4, "Pipe fracture: Sample 2 (suspected leak, debouncing)"),
    (24, 48, 2.2, 0.50, 51.8, "Pipe fracture: Sample 3 (confirmed flat leak -> throttle 25%)"),
    (8, 16, 1.0, 0.98, 57.2, "Critical protected reserve breached (<10% -> all valves 0%)"),
    (80, 160, 0.5, 0.50, 32.0, "Recovery after refill and pipe balance restoration"),
]

print(f"{'STAGE':<38} | {'TANK MODE':<11} | {'FLAT STATUS':<14} | {'MASTER':<6} | {'FLAT V':<6} | {'LEAK':<5} | {'ΔQ RATE':<9} | {'PRIORITY':<8}")
print("-" * 115)

for level, volume, flow_in, flow_out, current, label in READINGS:
    payload = {
        "device_id": DEVICE,
        "flat_id": FLAT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level_percent": level,
        "volume_l": volume,
        "flow_lpm": flow_in,
        "flow_out_lpm": flow_out,
        "ultrasonic_distance_cm": current,
        "sensor_status": "ok",
        "valve_percent": 100,
        "pump_on": False,
        "rssi": -55,
    }
    request = Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        data = json.loads(response.read().decode())
        leak_str = "YES" if data.get("leak_detected") else "NO"
        rate_str = f"{data.get('leak_rate_lpm', 0.0):.2f} L/m" if data.get("leak_detected") else "-"
        print(
            f"{label:<38} | "
            f"{data.get('tank_mode', data.get('mode', '')):<11} | "
            f"{data.get('flat_status', 'OK'):<14} | "
            f"{data.get('master_valve_percent', 0):>5.1f}% | "
            f"{data.get('flat_valve_percent', data.get('valve_percent', 0)):>5.1f}% | "
            f"{leak_str:<5} | "
            f"{rate_str:<9} | "
            f"{data.get('priority', ''):<8}"
        )
    sleep(1.5)
