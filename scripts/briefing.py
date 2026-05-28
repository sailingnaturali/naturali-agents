#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27", "paho-mqtt>=2.0"]
# ///
"""Daily briefing generator for s/v Naturali.

Fetches tides (CHS IWLS), passes a formatted data block to the Navigator agent
via hermes (which calls weather-mcp itself for wind/swell/buoys), then routes
the synthesized briefing to HA Lovelace (REST API), Nabu Voice (MQTT), and the
logbook (SQLite).

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

# Load ~/.hermes/.env so the script works when invoked directly (not via the bridge's export)
_env_file = os.path.expanduser("~/.hermes/.env")
if os.path.exists(_env_file):
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                if _k.strip() not in os.environ:
                    os.environ[_k.strip()] = _v.strip().strip('"').strip("'")

SIGNALK_URL = os.environ.get("SIGNALK_URL", "http://localhost:8765")
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


def build_prompt(
    tides: dict | None,
    lat: float,
    lon: float,
) -> str:
    parts: list[str] = [
        f"Generate the daily briefing. Vessel position: {lat:.4f}, {lon:.4f}.\n"
        "External data pre-fetched for you:\n"
    ]

    if tides:
        lines = [f"TIDES ({tides['station_name']}, {tides['distance_km']}km from vessel):"]
        for event in tides["events"]:
            dt = datetime.fromisoformat(event["time_utc"].replace("Z", "+00:00"))
            lines.append(f"  {event['type'].capitalize()}: {dt.strftime('%H:%M')} UTC — {event['height_m']}m")
        parts.append("\n".join(lines))
    else:
        parts.append("TIDES: unavailable — verify tide timing manually")

    parts.append(
        "Use your SignalK MCP tools to get current vessel state (position, wind, battery, route).\n"
        f"Call `mcp_weather_get_marine_forecast` with lat={lat:.4f}, lon={lon:.4f} for wind, "
        "swell, and seas. If conditions look borderline (wind 18–25 kn, or swell mattering), "
        "also call `mcp_weather_get_nearest_buoy_observations` to ground-truth against observed "
        "conditions from nearby NDBC buoys.\n"
        "Then synthesize the daily briefing.\n"
        'Respond with valid JSON only: {"briefing_markdown": "...", "tts_extract": "..."}\n'
        "briefing_markdown: full markdown with sections ## Weather, ## Navigation, ## Vessel Systems\n"
        "tts_extract: spoken summary, max 75 words, no markdown"
    )

    return "\n\n".join(parts)


def _is_response_line(line: str) -> bool:
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


def parse_briefing_response(text: str) -> dict | None:
    lines = [l for l in text.splitlines() if _is_response_line(l)]
    cleaned = "\n".join(lines).strip()
    if not cleaned:
        return None

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    if cleaned.startswith("```"):
        inner = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if inner.endswith("```"):
            inner = inner[: inner.rfind("```")]
        cleaned = inner.strip()

    try:
        data = json.loads(cleaned)
        if "briefing_markdown" in data and "tts_extract" in data:
            return data
        return None
    except json.JSONDecodeError:
        log.warning("parse_briefing_response: not valid JSON: %r", cleaned[:200])
        return None


def run_navigator(prompt: str) -> dict | None:
    log.info("invoking Navigator agent")
    try:
        result = subprocess.run(
            ["hermes", "chat", "-Q", "-s", AGENT_SKILL, "-q", prompt],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            log.error("hermes failed: %s", result.stderr.strip())
            return None
        return parse_briefing_response(result.stdout)
    except subprocess.TimeoutExpired:
        log.error("Navigator timed out after 120s")
        return None
    except FileNotFoundError:
        log.error("hermes not found on PATH")
        return None


def publish_to_ha(briefing_markdown: str) -> None:
    # HA state is capped at 255 chars — store full markdown in attributes instead
    r = httpx.post(
        f"{HA_URL}/api/states/sensor.daily_briefing",
        headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
        json={"state": "generated", "attributes": {"content": briefing_markdown, "friendly_name": "Daily Briefing"}},
        timeout=10,
    )
    r.raise_for_status()
    log.info("briefing published to HA")


def publish_tts(tts_extract: str) -> None:
    auth = {"username": MQTT_USER, "password": MQTT_PASSWORD} if MQTT_USER else None
    mqtt_publish.single(
        "naturali/agents/navigator/say",
        payload=json.dumps({"agent": "navigator", "text": tts_extract}),
        hostname=BROKER,
        port=PORT,
        auth=auth,
    )
    log.info("TTS extract published to MQTT")


def archive_to_logbook(briefing_markdown: str, db_path: str, lat: float, lon: float) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO marked_moments (text, timestamp, longitude, latitude) VALUES (?, ?, ?, ?)",
            (briefing_markdown, datetime.now(timezone.utc).isoformat(), lon, lat),
        )
    log.info("briefing archived to logbook")


def main(dry_run: bool = False) -> None:
    lat, lon = fetch_position()
    log.info("position: %.4f, %.4f", lat, lon)

    tides = fetch_tides(lat, lon)
    if tides is None:
        log.warning("tides fetch failed — briefing will note unavailability")

    prompt = build_prompt(tides, lat, lon)

    if dry_run:
        print(prompt)
        return

    response = run_navigator(prompt)
    if response is None:
        log.error("Navigator returned no response — aborting")
        return

    briefing_markdown = response["briefing_markdown"]
    tts_extract = response["tts_extract"]

    try:
        publish_to_ha(briefing_markdown)
    except Exception as e:
        log.error("publish_to_ha failed: %s", e)

    try:
        publish_tts(tts_extract)
    except Exception as e:
        log.error("publish_tts failed: %s", e)

    try:
        archive_to_logbook(briefing_markdown, LOGBOOK_DB_PATH, lat, lon)
    except Exception as e:
        log.error("archive_to_logbook failed: %s", e)

    log.info("briefing complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
