#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27", "paho-mqtt>=2.0"]
# ///
"""Daily briefing generator for s/v Naturali.

Fetches weather (Open-Meteo) and tides (CHS IWLS), passes a formatted data
block to the Navigator agent via hermes, then routes the synthesized briefing
to HA Lovelace (REST API), Nabu Voice (MQTT), and the logbook (SQLite).

Usage:
    uv run scripts/briefing.py             # full run
    uv run scripts/briefing.py --dry-run   # fetch data + print prompt, no hermes
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone

import httpx
import paho.mqtt.publish as mqtt_publish

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SIGNALK_URL = os.environ.get("SIGNALK_URL", "http://localhost:8765")
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
CHS_STATIONS_URL = "https://api-sine.dfo-mpo.gc.ca/api/v1/stations"
CHS_DATA_URL = "https://api-sine.dfo-mpo.gc.ca/api/v1/stations/{station_id}/data"
HA_URL = os.environ.get("HA_URL", "http://192.168.68.90:8123")
HA_TOKEN = os.environ.get("HOMEASSISTANT_TOKEN", "")
LOGBOOK_DB_PATH = os.environ.get("LOGBOOK_DB_PATH", os.path.expanduser("~/.naturali/logbook.db"))
BROKER = os.environ.get("MQTT_BROKER", "192.168.68.90")
PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD")
AGENT_SKILL = "naturali/navigator"
MOCK_LAT = 48.76   # Boundary Pass fallback
MOCK_LON = -123.05


def fetch_position() -> tuple[float, float]:
    pass


def fetch_weather(lat: float, lon: float) -> dict | None:
    pass


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    pass


def _nearest_tide_station(lat: float, lon: float, stations: list[dict]) -> dict:
    pass


def _classify_tide_events(events: list[dict]) -> list[dict]:
    pass


def fetch_tides(lat: float, lon: float) -> dict | None:
    pass


def _deg_to_compass(deg: float) -> str:
    pass


def build_prompt(
    weather: dict | None,
    tides: dict | None,
    lat: float,
    lon: float,
) -> str:
    pass


def _is_response_line(line: str) -> bool:
    pass


def parse_briefing_response(text: str) -> dict | None:
    pass


def run_navigator(prompt: str) -> dict | None:
    pass


def publish_to_ha(briefing_markdown: str) -> None:
    pass


def publish_tts(tts_extract: str) -> None:
    pass


def archive_to_logbook(briefing_markdown: str, db_path: str, lat: float, lon: float) -> None:
    pass


def main(dry_run: bool = False) -> None:
    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
