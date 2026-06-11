"""poseidon/config.py — env-driven settings (mirrors the bridge's style).

POSEIDON_ENV points at a KEY=VALUE file loaded at startup (default:
~/.hermes/.env, which already holds ANTHROPIC_API_KEY + MQTT creds — interim
arrangement until hermes is decommissioned). load_env_file never overrides
variables already present in the environment (launchd plist wins).
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

BROKER = os.environ.get("MQTT_BROKER", "192.168.68.90")
PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD")
CLIENT_ID = os.environ.get("MQTT_CLIENT_ID", "naturali-poseidon")
AGENT_NAME = os.environ.get("AGENT_NAME", "navigator")
SAY_TOPIC = f"naturali/agents/{AGENT_NAME}/say"
INTENTS_TOPIC = "naturali/intents/#"
ALERTS_TOPIC = "naturali/alerts/#"

MODEL = os.environ.get("POSEIDON_MODEL", "claude-sonnet-4-6")
ASK_TIMEOUT_S = float(os.environ.get("POSEIDON_ASK_TIMEOUT", "60"))
IDLE_RESET_S = float(os.environ.get("POSEIDON_IDLE_RESET", "1800"))
ROLLOVER_HOUR = int(os.environ.get("POSEIDON_ROLLOVER_HOUR", "6"))
ENV_FILE = os.environ.get("POSEIDON_ENV", os.path.expanduser("~/.hermes/.env"))


def load_env_file(path: str) -> None:
    """Load KEY=VALUE lines into os.environ without overriding existing vars."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        log.info("env file %s not found; relying on process environment", path)
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"'))
