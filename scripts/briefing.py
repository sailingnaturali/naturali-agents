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
    try:
        r = httpx.get(
            f"{SIGNALK_URL}/signalk/v1/api/vessels/self/navigation/position",
            timeout=5,
        )
        r.raise_for_status()
        pos = r.json().get("value", {})
        return float(pos["latitude"]), float(pos["longitude"])
    except Exception as e:
        log.warning("fetch_position failed (%s) — using mock position", e)
        return MOCK_LAT, MOCK_LON


def fetch_weather(lat: float, lon: float) -> dict | None:
    try:
        r = httpx.get(OPEN_METEO_URL, params={
            "latitude": lat, "longitude": lon,
            "hourly": "windspeed_10m,winddirection_10m,windgusts_10m,pressure_msl",
            "wind_speed_unit": "kn",
            "forecast_days": 1,
            "timezone": "auto",
        }, timeout=10)
        r.raise_for_status()
        data = r.json()
        h = datetime.now(timezone.utc).hour
        hourly = data["hourly"]

        # Pressure trend: compare to 6 hours ago
        prior = max(0, h - 6)
        pressure_delta = hourly["pressure_msl"][h] - hourly["pressure_msl"][prior]
        trend = "rising" if pressure_delta > 1 else "falling" if pressure_delta < -1 else "steady"

        # Afternoon wind (6 hours ahead, capped at last hour)
        afternoon = min(23, h + 6)
        afternoon_wind = round(hourly["windspeed_10m"][afternoon], 1)

        result = {
            "wind_knots": round(hourly["windspeed_10m"][h], 1),
            "wind_direction_deg": round(hourly["winddirection_10m"][h]),
            "wind_gust_knots": round(hourly["windgusts_10m"][h], 1),
            "pressure_hpa": round(hourly["pressure_msl"][h], 1),
            "pressure_trend": trend,
            "afternoon_wind_knots": afternoon_wind,
            "wave_height_m": None,
        }
    except Exception as e:
        log.warning("fetch_weather failed: %s", e)
        return None

    # Marine wave height — optional, failure OK
    try:
        mr = httpx.get(OPEN_METEO_MARINE_URL, params={
            "latitude": lat, "longitude": lon,
            "hourly": "wave_height",
            "forecast_days": 1,
            "timezone": "auto",
        }, timeout=10)
        mr.raise_for_status()
        result["wave_height_m"] = round(mr.json()["hourly"]["wave_height"][h], 1)
    except Exception:
        pass  # wave height unavailable — not fatal

    return result


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _nearest_tide_station(lat: float, lon: float, stations: list[dict]) -> dict:
    candidates = [
        s for s in stations
        if s.get("operating")
        and any(ts["code"] == "wlp-hilo" for ts in s.get("timeSeries", []))
    ]
    return min(candidates, key=lambda s: _haversine_km(lat, lon, s["latitude"], s["longitude"]))


def _classify_tide_events(events: list[dict]) -> list[dict]:
    if not events:
        return []
    first_is_high = len(events) < 2 or events[0]["value"] > events[1]["value"]
    types = ["high", "low"] if first_is_high else ["low", "high"]
    return [
        {"time_utc": e["eventDate"], "height_m": round(e["value"], 1), "type": types[i % 2]}
        for i, e in enumerate(events)
    ]


def fetch_tides(lat: float, lon: float) -> dict | None:
    try:
        sr = httpx.get(CHS_STATIONS_URL, timeout=15)
        sr.raise_for_status()
        station = _nearest_tide_station(lat, lon, sr.json())

        today = datetime.now(timezone.utc).date()
        tomorrow = today + timedelta(days=1)
        dr = httpx.get(
            CHS_DATA_URL.format(station_id=station["id"]),
            params={
                "time-series-code": "wlp-hilo",
                "from": f"{today}T00:00:00Z",
                "to": f"{tomorrow}T00:00:00Z",
            },
            timeout=15,
        )
        dr.raise_for_status()
        events = _classify_tide_events(dr.json())
        distance_km = round(_haversine_km(lat, lon, station["latitude"], station["longitude"]))
        return {
            "station_name": station["officialName"],
            "distance_km": distance_km,
            "events": events,
        }
    except Exception as e:
        log.warning("fetch_tides failed: %s", e)
        return None


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
