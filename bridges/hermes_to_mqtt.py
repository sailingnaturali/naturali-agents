#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["paho-mqtt>=2.0"]
# ///
"""Pipe Hermes agent output to MQTT for HA TTS broadcast.

Usage:
    hermes chat -Q -s naturali/navigator -q "What's the wind?" | uv run bridges/hermes_to_mqtt.py

Each line of stdin becomes one MQTT message on naturali/agents/{HERMES_AGENT}/say.
HA listens on that topic and routes to Piper TTS via the agent-voice automation.

Environment variables:
    MQTT_BROKER   hostname/IP of Mosquitto broker (default: naturali-signalk.local)
    MQTT_PORT     broker port (default: 1883)
    HERMES_AGENT  agent name used in topic path (default: navigator)
"""

from __future__ import annotations

import json
import os
import sys

import paho.mqtt.publish as publish


def main() -> None:
    broker = os.environ.get("MQTT_BROKER", "naturali-signalk.local")
    port = int(os.environ.get("MQTT_PORT", "1883"))
    agent = os.environ.get("HERMES_AGENT", "navigator")
    topic = f"naturali/agents/{agent}/say"

    lines = [line.rstrip("\n") for line in sys.stdin if line.strip()]
    if not lines:
        return

    # Join multi-line responses into a single message — Hermes sometimes wraps output.
    text = " ".join(lines)
    payload = json.dumps({"agent": agent, "text": text})

    publish.single(topic, payload=payload, hostname=broker, port=port)


if __name__ == "__main__":
    main()
