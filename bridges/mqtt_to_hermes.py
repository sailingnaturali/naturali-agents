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

Environment variables:
    MQTT_BROKER     hostname/IP of Mosquitto broker (default: naturali-signalk.local)
    MQTT_PORT       broker port (default: 1883)
    MQTT_USER       broker username (optional, for authenticated brokers)
    MQTT_PASSWORD   broker password (optional)
    HERMES_AGENT    skill name passed to hermes -s (default: naturali/navigator)

Intent topics → Hermes queries:
    naturali/intents/mark_moment  →  "Mark this moment in the logbook: {text}"
    naturali/intents/ask          →  "{text}"   (generic pass-through)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess

import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BROKER = os.environ.get("MQTT_BROKER", "naturali-signalk.local")
PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD")
AGENT_SKILL = os.environ.get("HERMES_AGENT", "naturali/navigator")


def _is_response_line(line: str) -> bool:
    """Return True only for lines that are actual agent response text."""
    s = line.strip()
    if not s:
        return False
    # Tool-call display lines (🔧 ...) and operational noise
    if s.startswith(("🔧", "⚠", "session_id:", "session:")):
        return False
    if s.startswith(("1.", "2.")) and ("model" in s or "threshold" in s or "compression" in s):
        return False
    if s.startswith(("auxiliary:", "compression:", "model:", "threshold:")):
        return False
    if "To make this permanent" in s or "edit config.yaml" in s:
        return False
    return True


def _run_hermes(query: str) -> None:
    """Run a single Hermes query and pipe the response to MQTT TTS."""
    log.info("hermes query: %s", query)
    try:
        result = subprocess.run(
            ["hermes", "chat", "-Q", "-s", AGENT_SKILL, "-q", query],
            capture_output=True,
            text=True,
            timeout=60,
        )
        lines = [l for l in result.stdout.splitlines() if _is_response_line(l)]
        response = " ".join(lines).strip()
        if response:
            log.info("hermes response: %s", response)
            # Publish to TTS topic directly — same format hermes_to_mqtt.py uses.
            import paho.mqtt.publish as publish
            topic = "naturali/agents/navigator/say"
            auth = {"username": MQTT_USER, "password": MQTT_PASSWORD} if MQTT_USER else None
            publish.single(topic, payload=json.dumps({"agent": "navigator", "text": response}), hostname=BROKER, port=PORT, auth=auth)
        if result.returncode != 0:
            log.error("hermes stderr: %s", result.stderr.strip())
    except subprocess.TimeoutExpired:
        log.error("hermes timed out for query: %s", query)


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
