import argparse
import json
import random
import time
from datetime import datetime, timedelta, timezone

import paho.mqtt.client as mqtt


def build_reading(level: float, scenario: str, timestamp: datetime) -> dict:
    flow = 2.0 + random.uniform(-0.15, 0.15)
    downstream = flow

    if scenario == "leak":
        downstream = flow * 0.72

    return {
        "device_id": "esp32-simulator",
        "timestamp": timestamp.isoformat(),
        "tank_level_percent": round(max(level, 0), 2),
        "flow_lpm": round(flow, 2),
        "downstream_flow_lpm": round(downstream, 2),
        "temperature_c": 36.0 if scenario == "shortage" else 29.0,
        "humidity_percent": 45.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish demo telemetry over MQTT.")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--topic", default="water/telemetry")
    parser.add_argument("--scenario", choices=["normal", "shortage", "leak"], default="normal")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument(
        "--sample-minutes",
        type=float,
        default=30.0,
        help="Virtual minutes between telemetry samples. Keeps quick demos realistic.",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=0,
        help="Number of samples to publish. Use 0 to publish until stopped.",
    )
    parser.add_argument(
        "--end-at-now",
        action="store_true",
        help="For fixed sample runs, backdate the first sample so the final sample is near now.",
    )
    args = parser.parse_args()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(args.host, args.port, keepalive=60)
    client.loop_start()

    level = 85.0
    sample_time = datetime.now(timezone.utc)
    if args.end_at_now and args.samples > 1:
        sample_time -= timedelta(minutes=args.sample_minutes * (args.samples - 1))

    published = 0
    try:
        while True:
            if args.samples and published >= args.samples:
                break

            if args.scenario == "normal":
                level += random.uniform(-0.1, 0.1)
            elif args.scenario == "shortage":
                level -= random.uniform(5.0, 8.0)
            elif args.scenario == "leak":
                level -= random.uniform(0.05, 0.15)

            level = min(max(level, 0), 100)
            reading = build_reading(level, args.scenario, sample_time)
            client.publish(args.topic, json.dumps(reading), qos=1)
            print(reading, flush=True)
            sample_time += timedelta(minutes=args.sample_minutes)
            published += 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
