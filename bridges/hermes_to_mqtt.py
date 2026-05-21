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
    MQTT_BROKER     hostname/IP of Mosquitto broker (default: naturali-signalk.local)
    MQTT_PORT       broker port (default: 1883)
    MQTT_USER       broker username (optional, for authenticated brokers)
    MQTT_PASSWORD   broker password (optional)
    HERMES_AGENT    agent name used in topic path (default: navigator)
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
    user = os.environ.get("MQTT_USER")
    password = os.environ.get("MQTT_PASSWORD")
    topic = f"naturali/agents/{agent}/say"

    # Filter out Hermes operational noise that leaks onto stdout in -Q mode:
    # session_id lines, ⚠ warnings, indented config suggestions.
    def _is_response(line: str) -> bool:
        s = line.strip()
        if not s:
            return False
        if s.startswith(("🔧", "⚠", "session_id:", "session:")):
            return False
        if s.startswith(("1.", "2.")) and ("model" in s or "threshold" in s or "compression" in s):
            return False
        if s.startswith(("auxiliary:", "compression:", "model:", "threshold:")):
            return False
        if "To make this permanent" in s or "edit config.yaml" in s:
            return False
        return True

    lines = [line.rstrip("\n") for line in sys.stdin if _is_response(line)]
    if not lines:
        return

    # Join multi-line responses — Hermes occasionally wraps long answers.
    text = " ".join(lines)
    payload = json.dumps({"agent": agent, "text": text})

    auth = {"username": user, "password": password} if user else None
    publish.single(topic, payload=payload, hostname=broker, port=port, auth=auth)


if __name__ == "__main__":
    main()
