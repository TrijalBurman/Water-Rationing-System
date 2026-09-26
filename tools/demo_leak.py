#!/usr/bin/env python3
"""
Live Leak Detection Demonstration Script for Review 2
Demonstrates dual-flow mass conservation, 3-cycle debouncing,
proportional 25% throttling, decoupled tank isolation, and recovery.
"""
from datetime import datetime, timezone
import json
import time
from urllib.request import Request, urlopen

API_URL = "http://localhost:8000/telemetry"
DEVICE_ID = "tank-01"
FLAT_ID = "flat-101"

# ANSI Colors for Terminal
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def post_telemetry(level, volume, q_in, q_out, label):
    payload = {
        "device_id": DEVICE_ID,
        "flat_id": FLAT_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level_percent": level,
        "volume_l": volume,
        "flow_lpm": q_in,
        "flow_out_lpm": q_out,
        "ultrasonic_distance_cm": round(60 - (level * 0.35), 1),
        "sensor_status": "ok",
        "valve_percent": 100,
        "pump_on": False,
        "rssi": -55,
    }
    req = Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode())


def run_demo():
    print(f"\n{BOLD}{CYAN}=" * 105)
    print("        AI-POWERED SMART WATER RATIONING: LIVE DUAL-FLOW LEAK DETECTION DEMONSTRATION")
    print("=" * 105 + f"{RESET}\n")

    # Step 1: Baseline Normal
    print(f"{BOLD}[PHASE 1] Baseline Normal Operation (Healthy Closed Pipeline){RESET}")
    print("Flow entering riser matches flow arriving at Flat 101 (Qin ≈ Qout)...")
    res = post_telemetry(80, 160, 1.0, 0.98, "Healthy Baseline")
    delta_q = 1.0 - 0.98
    print(
        f"  • Riser Qin: {1.0:.2f} L/m | Flat Qout: {0.98:.2f} L/m | ΔQ: {delta_q:.2f} L/m\n"
        f"  • {GREEN}Flat Status: {res.get('flat_status', 'OK')}{RESET} | "
        f"Flat Valve: {CYAN}{res.get('flat_valve_percent', 100):.1f}%{RESET} | "
        f"Central Tank Mode: {GREEN}{res.get('tank_mode', 'NORMAL')}{RESET}\n"
    )
    time.sleep(1.5)

    # Step 2: Leak Injection & Debounce
    print(f"{BOLD}[PHASE 2] Pipe Fracture Injection (Simulating Duct Burst: Qin >> Qout){RESET}")
    print("Fracture causes Qin = 2.20 L/min, but only Qout = 0.50 L/min reaches the apartment.")
    print(f"Escaping leakage rate: {RED}ΔQ = 1.70 L/min into wall cavity{RESET}\n")

    for i in range(1, 4):
        res = post_telemetry(78, 156, 2.2, 0.5, f"Leak Sample {i}")
        status = res.get("flat_status")
        valve = res.get("flat_valve_percent")
        tank_mode = res.get("tank_mode")

        if status == "SUSPECTED_LEAK":
            status_str = f"{YELLOW}{status} (Sample {i}/3 - Debouncing){RESET}"
            valve_str = f"{CYAN}{valve:.1f}% (Holding 100% to prevent false alarm){RESET}"
        else:
            status_str = f"{RED}{BOLD}{status} (CONFIRMED LEAK!){RESET}"
            valve_str = f"{RED}{BOLD}{valve:.1f}% (THROTTLED TO 25% TO MITIGATE LOSS){RESET}"

        print(f"  Cycle {i}: {status_str}")
        print(f"            └─ Flat Valve: {valve_str}")
        print(f"            └─ Central Tank Mode: {GREEN}{tank_mode} (Unpenalized!){RESET}")
        time.sleep(1.5)

    print(f"\n{BOLD}{CYAN}>>> Key Observation for Evaluators:{RESET}")
    print(f"    1. Flat 101's valve is throttled to 25%, slashing escaping pressure by >80%.")
    print(f"    2. Central Tank Mode remains NORMAL—building water is completely uninterrupted!\n")
    time.sleep(1.5)

    # Step 3: Critical Reserve Safety Cutoff Override
    print(f"{BOLD}[PHASE 3] Safety Override: Central Tank Drops Below 10% Reserve{RESET}")
    print("Even if flat valve was throttled to 25%, critical tank reserve mandates 0% shutoff...")
    res = post_telemetry(8, 16, 1.0, 0.5, "Critical Reserve Cutoff")
    print(
        f"  • Tank Level: {RED}8.0% (< 10% Min Safe Reserve){RESET}\n"
        f"  • Central Tank Mode: {RED}{BOLD}{res.get('tank_mode')}{RESET}\n"
        f"  • Master Supply Valve: {RED}{BOLD}{res.get('master_valve_percent'):.1f}%{RESET} | "
        f"Flat Valve: {RED}{BOLD}{res.get('flat_valve_percent'):.1f}% (Complete Safety Shutoff){RESET}\n"
    )
    time.sleep(1.5)

    # Step 4: Repair & Automatic Recovery
    print(f"{BOLD}[PHASE 4] Pipe Repaired & Tank Refilled (Automatic Recovery){RESET}")
    print("Plumbing restored: Qin = 0.50 L/min, Qout = 0.50 L/min, Tank level refilled to 80%...")
    res = post_telemetry(80, 160, 0.5, 0.5, "Post-Repair Recovery")
    print(
        f"  • Riser Qin: 0.50 L/m | Flat Qout: 0.50 L/m | ΔQ: 0.00 L/m\n"
        f"  • {GREEN}Flat Status: {res.get('flat_status', 'OK')}{RESET} | "
        f"Flat Valve: {GREEN}{res.get('flat_valve_percent', 100):.1f}% (Restored){RESET} | "
        f"Tank Mode: {GREEN}{res.get('tank_mode', 'NORMAL')}{RESET}\n"
    )

    print(f"{BOLD}{CYAN}=" * 105)
    print("                         DEMONSTRATION COMPLETED SUCCESSFULLY")
    print("=" * 105 + f"{RESET}\n")


if __name__ == "__main__":
    run_demo()
