"""GPS Simulator Script for Development & Testing.

Publishes simulated vehicle telemetry over MQTT to the specified broker and topic.
Generates realistic coordinate movement and speed telemetry at configurable intervals.

Usage:
  python scripts/gps_simulator.py --vehicle-id 1 --interval 2.0
"""

import argparse
import json
import math
import os
import random
import sys
import time
from datetime import datetime, timezone

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Error: 'paho-mqtt' package is required. Install with: pip install paho-mqtt")
    sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(description="GPS Telemetry Simulator")
    parser.add_argument(
        "--host",
        default=os.getenv("MQTT_BROKER_HOST", "localhost"),
        help="MQTT broker host (default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MQTT_BROKER_PORT", "1883")),
        help="MQTT broker port (default: 1883)",
    )
    parser.add_argument(
        "--vehicle-id",
        type=int,
        default=1,
        help="Vehicle ID to simulate (default: 1)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Publish interval in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=0,
        help="Total messages to publish (0 for continuous infinite mode)",
    )
    parser.add_argument(
        "--start-lat",
        type=float,
        default=11.0168,
        help="Starting latitude in decimal degrees (default: 11.0168)",
    )
    parser.add_argument(
        "--start-lng",
        type=float,
        default=76.9558,
        help="Starting longitude in decimal degrees (default: 76.9558)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    topic = f"vehicles/{args.vehicle_id}/gps"

    # Construct Paho client with version compatibility
    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    else:
        client = mqtt.Client()


    print(f"Connecting to MQTT broker at {args.host}:{args.port}...")
    try:
        client.connect(args.host, args.port, 60)
        client.loop_start()
        print(f"Connected! Publishing GPS updates for Vehicle #{args.vehicle_id} to '{topic}' every {args.interval}s.")
        print("Press Ctrl+C to stop.\n")
    except Exception as exc:
        print(f"Failed to connect to MQTT broker at {args.host}:{args.port}: {exc}")
        sys.exit(1)

    lat = args.start_lat
    lng = args.start_lng
    angle = 0.0
    step = 0

    try:
        while True:
            step += 1

            # Simulate circular/curved route movement (~0.0005 deg delta per step)
            angle += 0.1
            lat += 0.0003 * math.sin(angle) + random.uniform(-0.00005, 0.00005)
            lng += 0.0003 * math.cos(angle) + random.uniform(-0.00005, 0.00005)
            speed = round(max(0.0, 35.0 + 10.0 * math.sin(angle * 2) + random.uniform(-2.0, 2.0)), 1)
            timestamp = datetime.now(timezone.utc).isoformat()

            payload = {
                "vehicle_id": args.vehicle_id,
                "latitude": round(lat, 6),
                "longitude": round(lng, 6),
                "speed": speed,
                "timestamp": timestamp,
            }

            payload_json = json.dumps(payload)
            result = client.publish(topic, payload_json, qos=1)

            print(f"[{step}] Published to {topic} (rc={result.rc}): {payload_json}")

            if args.count > 0 and step >= args.count:
                print(f"\nCompleted publishing {args.count} messages.")
                break

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\nSimulator stopped by user.")
    finally:
        client.loop_stop()
        client.disconnect()
        print("MQTT client disconnected.")


if __name__ == "__main__":
    main()