#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["paho-mqtt>=2.0"]
# ///
"""Listen for HA voice intents on MQTT, dispatch to Hermes.

Run this as a persistent background service on the Mac Studio.
It subscribes to naturali/intents/# and maps each intent to a Hermes query.

Usage:
    uv run bridges/mqtt_to_hermes.py

Environment variables — see SPEC.md for the canonical table.

Intent topics → Hermes queries:
    naturali/intents/mark_moment  →  "Mark this moment in the logbook: {text}"
    naturali/intents/ask          →  "{text}"   (generic pass-through)
    naturali/intents/briefing     →  runs briefing.py (handles its own outputs)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess

import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish

from _filter import is_response_line

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BROKER = os.environ.get("MQTT_BROKER", "naturali-signalk.local")
PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD")
AGENT_NAME = os.environ.get("AGENT_NAME", "navigator")
HERMES_SKILL = os.environ.get("HERMES_SKILL", "naturali/navigator")
SAY_TOPIC = f"naturali/agents/{AGENT_NAME}/say"


def _run_hermes(query: str) -> None:
    """Run a single Hermes query and pipe the response to MQTT TTS."""
    log.info("hermes query: %s", query)
    try:
        result = subprocess.run(
            ["hermes", "chat", "-Q", "-s", HERMES_SKILL, "-q", query],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        log.error("hermes timed out for query: %s", query)
        return

    if result.returncode != 0:
        log.error("hermes exit=%d stderr: %s", result.returncode, result.stderr.strip())
        return

    lines = [l for l in result.stdout.splitlines() if is_response_line(l)]
    response = " ".join(lines).strip()
    if not response:
        return

    log.info("hermes response: %s", response)
    auth = {"username": MQTT_USER, "password": MQTT_PASSWORD} if MQTT_USER else None
    publish.single(
        SAY_TOPIC,
        payload=json.dumps({"agent": AGENT_NAME, "text": response}),
        hostname=BROKER,
        port=PORT,
        auth=auth,
    )


def _run_briefing() -> None:
    """Invoke briefing.py as a subprocess. It handles all publishing internally."""
    log.info("triggering daily briefing generation")
    scripts_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "scripts")
    )
    briefing_script = os.path.join(scripts_dir, "briefing.py")
    try:
        result = subprocess.run(
            ["uv", "run", briefing_script],
            timeout=180,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            log.error("briefing.py failed (rc=%d): %s", result.returncode, result.stderr.strip())
        else:
            log.info("briefing complete")
    except subprocess.TimeoutExpired:
        log.error("briefing.py timed out after 180s")


def on_connect(client: mqtt.Client, userdata: None, flags: dict, rc: int, properties=None) -> None:
    if rc == 0:
        log.info("connected to %s:%d", BROKER, PORT)
        client.subscribe("naturali/intents/#")
        log.info("subscribed to naturali/intents/#")
    else:
        log.error("connection failed, rc=%d", rc)


def on_message(client: mqtt.Client, userdata: None, msg: mqtt.MQTTMessage) -> None:
    topic = msg.topic
    try:
        payload = json.loads(msg.payload.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = {"text": msg.payload.decode(errors="replace")}

    text = payload.get("text", "").strip()
    log.info("intent: %s payload=%s", topic, payload)

    if topic == "naturali/intents/mark_moment":
        query = f"Mark this moment in the logbook: {text}" if text else "Mark this moment in the logbook."
        _run_hermes(query)
    elif topic == "naturali/intents/ask":
        if text:
            _run_hermes(text)
    elif topic == "naturali/intents/briefing":
        _run_briefing()
    else:
        log.warning("unhandled intent topic: %s", topic)


def main() -> None:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

    log.info("connecting to %s:%d", BROKER, PORT)
    client.connect(BROKER, PORT, keepalive=60)
    client.loop_forever()


if __name__ == "__main__":
    main()
