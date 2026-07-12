"""poseidon/mute_publish.py — retained-MQTT mute publish (shared daemon + mutes-mcp).

Moved from daemon.py so the standalone mutes MCP server can publish without
importing the daemon. Topic contract: retained envelope per category on
naturali/mutes/<category>; empty retained payload deletes the slot.
"""
from __future__ import annotations

import json

import paho.mqtt.publish as mqtt_publish

from poseidon import config


def publish_mute_clear(category: str) -> None:
    """Delete a retained mute slot (empty retained payload)."""
    auth = ({"username": config.MQTT_USER, "password": config.MQTT_PASSWORD}
            if config.MQTT_USER else None)
    mqtt_publish.single(f"{config.MUTES_TOPIC_PREFIX}/{category}", payload=None,
                        retain=True, hostname=config.BROKER, port=config.PORT,
                        auth=auth)


def publish_mute_set(category: str, envelope: dict) -> None:
    """Publish a retained mute envelope."""
    auth = ({"username": config.MQTT_USER, "password": config.MQTT_PASSWORD}
            if config.MQTT_USER else None)
    mqtt_publish.single(f"{config.MUTES_TOPIC_PREFIX}/{category}",
                        payload=json.dumps(envelope), retain=True,
                        hostname=config.BROKER, port=config.PORT, auth=auth)
