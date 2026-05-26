#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["paho-mqtt>=2.0"]
# ///
"""Pipe Hermes agent output to MQTT for HA TTS broadcast.

Usage:
    hermes chat -Q -s naturali/navigator -q "What's the wind?" | uv run bridges/hermes_to_mqtt.py

Each line of stdin is filtered (see _filter.py) and joined into one MQTT
message on naturali/agents/{AGENT_NAME}/say. HA listens on that topic and
routes to Piper TTS via the agent-voice automation.

Environment variables — see SPEC.md for the canonical table.
"""

from __future__ import annotations

import json
import os
import sys

import paho.mqtt.publish as publish

from _filter import is_response_line


def main() -> None:
    broker = os.environ.get("MQTT_BROKER", "naturalaspi.local")
    port = int(os.environ.get("MQTT_PORT", "1883"))
    agent = os.environ.get("AGENT_NAME", "navigator")
    user = os.environ.get("MQTT_USER")
    password = os.environ.get("MQTT_PASSWORD")
    topic = f"naturali/agents/{agent}/say"

    lines = [line.rstrip("\n") for line in sys.stdin if is_response_line(line)]
    if not lines:
        return

    # Join multi-line responses — Hermes occasionally wraps long answers.
    text = " ".join(lines)
    payload = json.dumps({"agent": agent, "text": text})

    auth = {"username": user, "password": password} if user else None
    publish.single(topic, payload=payload, hostname=broker, port=port, auth=auth)


if __name__ == "__main__":
    main()
