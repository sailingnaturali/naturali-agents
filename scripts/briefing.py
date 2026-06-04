#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27", "paho-mqtt>=2.0", "jinja2>=3.1"]
# ///
"""Daily briefing generator for the active vessel.

Fetches tides (CHS IWLS) and an hourly wind series, passes a data block to the
Navigator agent via hermes (which calls weather-mcp itself for wind/swell/buoys),
then renders the synthesized structured briefing into a self-contained HTML
document. Routes outputs to HA (HTML scp'd to /config/www + a state sensor),
Nabu Voice (MQTT TTS), and the logbook (SQLite, as deterministic markdown).

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
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

import httpx
import paho.mqtt.publish as mqtt_publish
from jinja2 import Environment, FileSystemLoader, select_autoescape

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
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
HA_URL = os.environ.get("HA_URL", "http://192.168.68.90:8123")
HA_TOKEN = os.environ.get("HOMEASSISTANT_TOKEN", "")
LOGBOOK_DB_PATH = os.environ.get("LOGBOOK_DB_PATH", os.path.expanduser("~/.naturali/logbook.db"))
BROKER = os.environ.get("MQTT_BROKER", "192.168.68.90")
PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD")
AGENT_SKILL = "naturali/navigator"
# Direct Ollama endpoint for the structured-output repair pass (bypasses hermes;
# reformatting needs no tools). qwen2.5:72b is the most capable local model;
# grammar-constrained decoding guarantees valid JSON regardless.
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_REPAIR_MODEL = os.environ.get("OLLAMA_REPAIR_MODEL", "qwen2.5:72b")
MOCK_LAT = 48.76   # Boundary Pass fallback
MOCK_LON = -123.05
HA_SSH_HOST = os.environ.get("HA_SSH_HOST", "root@192.168.68.90")
HA_WWW_PATH = "/config/www/briefing.html"
_TEMPLATE_DIR = Path(__file__).parent / "templates"

# The exact JSON shape the briefing must produce. Shared by the synthesis prompt
# and the repair pass so they can never drift apart.
SCHEMA_EXAMPLE = (
    '{"briefing": {'
    '"header": {"date": "June 1", "position": "Oak Bay", "destination": "Sidney"}, '
    '"weather": {"rows": [{"source": "Forecast", "wind": "5 kn W", "pressure": "1018 steady"}], '
    '"analysis": "Settled under high pressure."}, '
    '"navigation": {"tide_rows": [{"type": "High", "time": "12:38", "height": "3.8 m"}], '
    '"departure": "0900 to carry the flood", "analysis": "Slack favours mid-morning."}, '
    '"vessel_systems": {"notes": ["Engine hours logged; bilge dry."]}, '
    '"advisories": [{"level": "info", "text": "Battery 68% — full range available."}]}, '
    '"tts_extract": "Good morning. Light westerlies, settled. Depart by 0900 for the flood."}'
)

# JSON Schema form of SCHEMA_EXAMPLE — fed to Ollama's `format` so the repair pass
# is grammar-constrained to emit exactly this shape (can't return prose).
_ROW = lambda props: {  # noqa: E731
    "type": "array",
    "items": {"type": "object", "properties": props, "required": list(props)},
}
BRIEFING_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "briefing": {
            "type": "object",
            "properties": {
                "header": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string"},
                        "position": {"type": "string"},
                        "destination": {"type": "string"},
                    },
                    "required": ["date", "position", "destination"],
                },
                "weather": {
                    "type": "object",
                    "properties": {
                        "rows": _ROW({"source": {"type": "string"}, "wind": {"type": "string"}, "pressure": {"type": "string"}}),
                        "analysis": {"type": "string"},
                    },
                    "required": ["rows", "analysis"],
                },
                "navigation": {
                    "type": "object",
                    "properties": {
                        "tide_rows": _ROW({"type": {"type": "string"}, "time": {"type": "string"}, "height": {"type": "string"}}),
                        "departure": {"type": "string"},
                        "analysis": {"type": "string"},
                    },
                    "required": ["tide_rows", "departure", "analysis"],
                },
                "vessel_systems": {
                    "type": "object",
                    "properties": {"notes": {"type": "array", "items": {"type": "string"}}},
                    "required": ["notes"],
                },
                "advisories": _ROW({"level": {"type": "string"}, "text": {"type": "string"}}),
            },
            "required": ["header", "weather", "navigation", "vessel_systems", "advisories"],
        },
        "tts_extract": {"type": "string"},
    },
    "required": ["briefing", "tts_extract"],
}


class TankSpec(NamedTuple):
    key: str          # SignalK tanks/<key> path segment
    label: str
    direction: str    # "fill" → concern is reaching 100%; "drain" → reaching 0%
    action: str       # guidance text shown with the ETA


TANKS = [
    TankSpec("blackWater", "Black Water", "fill", "pump out"),
    TankSpec("freshWater", "Fresh Water", "drain", "run the water maker / fill soon"),
]


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


def reverse_geocode(lat: float, lon: float) -> str | None:
    """Resolve a place name for the vessel position (header shows a name, not coords).

    Online (Nominatim) — returns None when offline so the caller can fall back.
    """
    try:
        r = httpx.get(
            NOMINATIM_URL,
            params={"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 14},
            headers={"User-Agent": "naturali-briefing/1.0 (+https://sailingnaturali.com)"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning("reverse_geocode failed (%s) — position name unavailable", e)
        return None
    addr = data.get("address", {})
    for key in ("hamlet", "village", "town", "city", "suburb", "neighbourhood", "municipality"):
        if addr.get(key):
            return addr[key]
    return data.get("name") or None


def fetch_destination() -> str | None:
    """Destination name from SignalK's active route. None when not navigating.

    Reads the v2 course API; if a route is active, resolves the route resource
    for a human name. Returns None (→ header omits destination) when there is no
    active route or SignalK is unreachable.
    """
    try:
        r = httpx.get(f"{SIGNALK_URL}/signalk/v2/api/vessels/self/navigation/course", timeout=5)
        r.raise_for_status()
        course = r.json()
    except Exception as e:
        log.warning("fetch_destination: course API unavailable (%s)", e)
        return None

    active = course.get("activeRoute") or {}
    href = active.get("href")
    if not href:
        return None  # not navigating a route

    url = f"{SIGNALK_URL}/signalk/v2/api{href}" if href.startswith("/") else f"{SIGNALK_URL}/{href}"
    try:
        rr = httpx.get(url, timeout=5)
        rr.raise_for_status()
        route = rr.json()
    except Exception as e:
        log.warning("fetch_destination: route resource %s unavailable (%s)", href, e)
        return None

    if route.get("name"):
        return route["name"]
    # GeoJSON LineString route: last coordinate's waypoint name, if present.
    try:
        coords = route["feature"]["geometry"]["coordinates"]
        names = route["feature"]["properties"].get("coordinatesMeta") or []
        if names and names[-1].get("name"):
            return names[-1]["name"]
        if coords:
            lon, lat = coords[-1][0], coords[-1][1]
            return reverse_geocode(lat, lon)
    except (KeyError, IndexError, TypeError):
        pass
    return None


def fetch_vessel_name() -> str:
    """Vessel name for display. ``$VESSEL_NAME`` wins; else SignalK's self
    name; else "Naturali". SignalK is fed from the active vessel profile, so
    the briefing names the boat it's actually reporting on without edits.
    """
    env_name = os.environ.get("VESSEL_NAME")
    if env_name and env_name.strip():
        return env_name.strip()
    try:
        r = httpx.get(f"{SIGNALK_URL}/signalk/v1/api/vessels/self/name", timeout=5)
        r.raise_for_status()
        name = r.json()
        if isinstance(name, str) and name.strip():
            return name.strip()
    except Exception as e:
        log.warning("fetch_vessel_name: name unavailable (%s)", e)
    return "Naturali"


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


def fetch_tide_curve(lat: float, lon: float) -> list[dict] | None:
    """Fetch the continuous (wlp) water-level series for the SVG tide curve.

    Spans the **local** calendar day (midnight→midnight local) so the chart's
    x-axis reads 00:00–24:00 local. Uses the same nearest-station selection as
    fetch_tides. Returns a list of {"time_utc", "height_m"} or None.
    """
    try:
        sr = httpx.get(CHS_STATIONS_URL, timeout=15)
        sr.raise_for_status()
        station = _nearest_tide_station(lat, lon, sr.json())

        start_local = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(days=1)
        dr = httpx.get(
            CHS_DATA_URL.format(station_id=station["id"]),
            params={
                "time-series-code": "wlp",
                "from": start_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "to": end_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            timeout=15,
        )
        dr.raise_for_status()
        return [
            {"time_utc": e["eventDate"], "height_m": round(e["value"], 2)}
            for e in dr.json()
        ]
    except Exception as e:
        log.warning("fetch_tide_curve failed: %s", e)
        return None


def fetch_current_wind(lat: float, lon: float) -> dict | None:
    """Current wind (speed in knots + direction in degrees) for the compass.

    Open-Meteo current conditions — weather *synthesis* still goes through the
    Navigator/weather-mcp. Returns {"speed_kn", "direction_deg"} or None.
    direction_deg is the meteorological bearing the wind blows FROM.
    """
    try:
        r = httpx.get(
            OPEN_METEO_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "wind_speed_10m,wind_direction_10m",
                "wind_speed_unit": "kn",
                "timezone": "auto",
            },
            timeout=15,
        )
        r.raise_for_status()
        cur = r.json()["current"]
        return {
            "speed_kn": float(cur["wind_speed_10m"]),
            "direction_deg": float(cur["wind_direction_10m"]),
        }
    except Exception as e:
        log.warning("fetch_current_wind failed: %s", e)
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
        "also call `mcp_weather_get_nearest_buoy_observations` to ground-truth.\n"
        "Then synthesize the daily briefing. Respond with ONE valid JSON object and "
        "nothing else — no preamble, no markdown fences, no template placeholders. "
        "Fill every field with real values from the data. Match this shape exactly:\n"
        f"{SCHEMA_EXAMPLE}\n"
        "tts_extract: spoken summary, max 75 words, no markdown."
    )

    return "\n\n".join(parts)


_CARDINALS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def cardinal(direction_deg: float) -> str:
    """16-point-rounded-to-8 cardinal label for a bearing in degrees."""
    return _CARDINALS[round((direction_deg % 360) / 45) % 8]


def build_wind_compass(direction_deg: float | None, speed_kn: float | None) -> str:
    """Inline SVG wind dial (Apple-Weather style): a graduated ring, a pin at the
    source bearing, and a bold arrow flying downwind, with the speed at centre.

    direction_deg is the meteorological bearing the wind blows FROM. Pure
    function; returns "" when inputs are missing.
    """
    if direction_deg is None or speed_kn is None:
        return ""

    cx = cy = 80.0
    r = 70.0
    th = math.radians(direction_deg)          # FROM bearing
    th2 = th + math.pi                         # downwind (TO) bearing

    parts = [
        '<svg viewBox="0 0 160 160" xmlns="http://www.w3.org/2000/svg" '
        f'class="compass" role="img" aria-label="Wind {speed_kn:.0f} kn from {cardinal(direction_deg)}">'
    ]
    # graduated tick ring (every 5°, longer + brighter at the 8 points)
    for deg in range(0, 360, 5):
        a = math.radians(deg)
        major = deg % 45 == 0
        t_in = r - (10 if major else 5)
        x1, y1 = cx + t_in * math.sin(a), cy - t_in * math.cos(a)
        x2, y2 = cx + r * math.sin(a), cy - r * math.cos(a)
        parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{"#475569" if major else "#283447"}" stroke-width="{1.6 if major else 1}"/>')
    for label, deg in (("N", 0), ("E", 90), ("S", 180), ("W", 270)):
        a = math.radians(deg)
        lxp, lyp = cx + (r - 22) * math.sin(a), cy - (r - 22) * math.cos(a)
        parts.append(f'<text x="{lxp:.1f}" y="{lyp + 4:.1f}" fill="#94a3b8" font-size="12" text-anchor="middle">{label}</text>')
    # source pin (where the wind is FROM): stem + dot on the ring
    px, py = cx + (r - 6) * math.sin(th), cy - (r - 6) * math.cos(th)
    sx, sy = cx + (r - 20) * math.sin(th), cy - (r - 20) * math.cos(th)
    parts.append(f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{px:.1f}" y2="{py:.1f}" stroke="#5eead4" stroke-width="2"/>')
    parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="#e5e7eb"/>')
    # downwind arrow (the direction the wind blows TO), offset into that quadrant
    t1, t2 = r * 0.30, r * 0.62               # shaft along downwind bearing
    ax1, ay1 = cx + t1 * math.sin(th2), cy - t1 * math.cos(th2)
    ax2, ay2 = cx + t2 * math.sin(th2), cy - t2 * math.cos(th2)
    ah = math.atan2(ay2 - ay1, ax2 - ax1)
    hl, hw = 13.0, 8.0
    bx, by = ax2 - hl * math.cos(ah), ay2 - hl * math.sin(ah)
    lx, ly = bx - hw * math.sin(ah), by + hw * math.cos(ah)
    rxp, ryp = bx + hw * math.sin(ah), by - hw * math.cos(ah)
    parts.append(f'<line x1="{ax1:.1f}" y1="{ay1:.1f}" x2="{bx:.1f}" y2="{by:.1f}" stroke="#e5e7eb" stroke-width="4" stroke-linecap="round"/>')
    parts.append(f'<polygon points="{ax2:.1f},{ay2:.1f} {lx:.1f},{ly:.1f} {rxp:.1f},{ryp:.1f}" fill="#e5e7eb"/>')
    # centre speed
    parts.append(f'<text x="{cx}" y="{cy - 1:.1f}" fill="#e5e7eb" font-size="26" font-weight="700" text-anchor="middle">{speed_kn:.0f}</text>')
    parts.append(f'<text x="{cx}" y="{cy + 15:.1f}" fill="#94a3b8" font-size="11" text-anchor="middle">kn</text>')
    parts.append("</svg>")
    return "".join(parts)


def build_tide_chart(tide: list[dict] | None) -> str:
    """Inline SVG area chart of tide height over the day, with labelled axes.

    tide is fetch_tide_curve output [{"time_utc", "height_m"}]. Pure function;
    returns "" when there is no data. Y-axis is metres; X-axis is local time.
    """
    if not tide:
        return ""

    # Downsample the (often per-minute) series to keep the SVG small; the curve
    # is smooth so ~180 points is visually identical.
    MAXP = 180
    if len(tide) > MAXP:
        step = len(tide) / MAXP
        tide = [tide[int(i * step)] for i in range(MAXP)] + [tide[-1]]

    W, H = 720, 240
    L, R_, T, B = 46, 14, 18, 30  # paddings (left=y-labels, bottom=x-labels)
    plot_w, plot_h = W - L - R_, H - T - B
    base_y = T + plot_h

    heights = [p["height_m"] for p in tide]
    times = []
    for p in tide:
        try:
            times.append(datetime.fromisoformat(p["time_utc"].replace("Z", "+00:00")).astimezone())
        except Exception:
            times.append(None)

    lo, hi = min(heights), max(heights)
    pad_v = (hi - lo) * 0.1 or 0.1
    lo_a, hi_a = lo - pad_v, hi + pad_v
    span_a = hi_a - lo_a
    n = len(tide)

    def X(i: int) -> float:
        return L + plot_w * (i / (n - 1) if n > 1 else 0.5)

    def Y(v: float) -> float:
        return T + plot_h * (1 - (v - lo_a) / span_a)

    parts = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" class="tide" role="img" aria-label="Tide height over the day">']
    # horizontal gridlines + metre labels
    for v in (lo, (lo + hi) / 2, hi):
        y = Y(v)
        parts.append(f'<line x1="{L}" y1="{y:.1f}" x2="{W - R_}" y2="{y:.1f}" stroke="#1e293b" stroke-width="1"/>')
        parts.append(f'<text x="{L - 8}" y="{y + 4:.1f}" fill="#94a3b8" font-size="12" text-anchor="end">{v:.1f} m</text>')
    # vertical gridlines + local-time labels (5 ticks)
    ticks = 4
    for k in range(ticks + 1):
        i = round((n - 1) * k / ticks)
        x = X(i)
        parts.append(f'<line x1="{x:.1f}" y1="{T}" x2="{x:.1f}" y2="{base_y}" stroke="#1e293b" stroke-width="1"/>')
        lbl = times[i].strftime("%H:%M") if times[i] else ""
        parts.append(f'<text x="{x:.1f}" y="{H - B + 18:.1f}" fill="#94a3b8" font-size="12" text-anchor="middle">{lbl}</text>')
    # area fill + line
    line_pts = " ".join(f"{X(i):.1f},{Y(h):.1f}" for i, h in enumerate(heights))
    parts.append(f'<polygon points="{X(0):.1f},{base_y:.1f} {line_pts} {X(n - 1):.1f},{base_y:.1f}" fill="#fbbf24" fill-opacity="0.15"/>')
    parts.append(f'<polyline points="{line_pts}" fill="none" stroke="#fbbf24" stroke-width="2.5"/>')
    # hi/lo dots
    for i, h in enumerate(heights):
        if h in (hi, lo):
            parts.append(f'<circle cx="{X(i):.1f}" cy="{Y(h):.1f}" r="3.5" fill="#fbbf24"/>')
    # "now" marker, only if inside the data window
    now = datetime.now().astimezone()
    if times[0] and times[-1] and times[0] <= now <= times[-1]:
        ni = min(range(n), key=lambda i: abs((times[i] - now).total_seconds()) if times[i] else 1e18)
        xn = X(ni)
        parts.append(f'<line x1="{xn:.1f}" y1="{T}" x2="{xn:.1f}" y2="{base_y}" stroke="#5eead4" stroke-width="1.5" stroke-dasharray="4 3"/>')
        parts.append(f'<text x="{xn:.1f}" y="{T + 10:.1f}" fill="#5eead4" font-size="11" text-anchor="middle">now</text>')
    parts.append("</svg>")
    return "".join(parts)


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

    # Local models sometimes wrap the JSON in stray preamble/postamble or
    # pseudo-tags (e.g. "<no_preliminary nor_results_from_me>"). Fall back to
    # the outermost {...} span so the object survives surrounding noise.
    candidates = [cleaned]
    first, last = cleaned.find("{"), cleaned.rfind("}")
    if first != -1 and last > first:
        span = cleaned[first : last + 1]
        if span != cleaned:
            candidates.append(span)

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if "briefing" in data and "tts_extract" in data:
            return data
        return None

    log.warning("parse_briefing_response: not valid JSON: %r", cleaned[:200])
    return None


def _hermes_query(prompt: str, timeout: int = 120) -> str | None:
    """Run one hermes/Navigator query; return raw stdout or None on failure."""
    try:
        result = subprocess.run(
            ["hermes", "chat", "-Q", "-s", AGENT_SKILL, "-q", prompt],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        log.error("Navigator timed out after %ds", timeout)
        return None
    except FileNotFoundError:
        log.error("hermes not found on PATH")
        return None
    if result.returncode != 0:
        log.error("hermes failed: %s", result.stderr.strip())
        return None
    return result.stdout


def repair_to_json(prose: str) -> dict | None:
    """Second pass: reformat free-form briefing prose into the strict JSON shape.

    Local models often answer the synthesis prompt in prose despite the
    'JSON only' instruction, yet still produce the right *content*. This pass
    calls Ollama directly with `format` set to BRIEFING_JSON_SCHEMA, so decoding
    is grammar-constrained — the model *cannot* emit anything but schema-valid
    JSON. Reformatting needs no tools, so bypassing hermes is fine; stays fully
    offline on the boat.
    """
    log.info("Navigator response was not JSON — repairing via Ollama structured output")
    payload = {
        "model": OLLAMA_REPAIR_MODEL,
        "format": BRIEFING_JSON_SCHEMA,
        "stream": False,
        "options": {"temperature": 0},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You reformat a sailing briefing into JSON. Use only the real "
                    "values present in the user's text. Do not invent data; if a "
                    "field is absent, use an empty string or empty list."
                ),
            },
            {"role": "user", "content": prose.strip()},
        ],
    }
    try:
        r = httpx.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=120)
        r.raise_for_status()
        content = r.json()["message"]["content"]
    except Exception as e:
        log.error("JSON repair pass (Ollama) failed: %s", e)
        return None

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        log.error("JSON repair returned non-JSON despite schema: %s", e)
        return None
    if "briefing" in data and "tts_extract" in data:
        return data
    log.error("JSON repair produced JSON missing required keys")
    return None


def run_navigator(prompt: str) -> dict | None:
    log.info("invoking Navigator agent")
    raw = _hermes_query(prompt)
    if raw is None:
        return None
    parsed = parse_briefing_response(raw)
    if parsed is not None:
        return parsed
    # Model ignored the 'JSON only' instruction — salvage the prose.
    return repair_to_json(raw)


def publish_to_ha(state: str = "generated") -> None:
    r = httpx.post(
        f"{HA_URL}/api/states/sensor.daily_briefing",
        headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
        json={"state": state, "attributes": {"friendly_name": "Daily Briefing"}},
        timeout=10,
    )
    r.raise_for_status()
    log.info("briefing state published to HA")


def publish_html(html: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(html)
        tmp = f.name
    try:
        result = subprocess.run(
            ["scp", "-o", "BatchMode=yes", tmp, f"{HA_SSH_HOST}:{HA_WWW_PATH}"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"scp failed: {result.stderr.strip()}")
        log.info("briefing HTML published to HA www")
    finally:
        os.unlink(tmp)


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


_TANK_DDL = """CREATE TABLE IF NOT EXISTS tank_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tank TEXT NOT NULL,
    level REAL NOT NULL,
    timestamp TEXT NOT NULL
)"""


def fetch_tank_level(key: str) -> float | None:
    """Current level (percent 0-100) for a SignalK tank type, or None if absent."""
    try:
        r = httpx.get(f"{SIGNALK_URL}/signalk/v1/api/vessels/self/tanks/{key}", timeout=5)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning("fetch_tank_level(%s) unavailable (%s)", key, e)
        return None
    for instance in (data or {}).values():
        cl = instance.get("currentLevel") if isinstance(instance, dict) else None
        val = cl.get("value") if isinstance(cl, dict) else None
        if isinstance(val, (int, float)):
            return round(val * 100, 1)
    return None


def record_tank_reading(key: str, level_pct: float, db_path: str | None = None) -> None:
    with sqlite3.connect(db_path or LOGBOOK_DB_PATH) as conn:
        conn.execute(_TANK_DDL)
        conn.execute(
            "INSERT INTO tank_readings (tank, level, timestamp) VALUES (?, ?, ?)",
            (key, level_pct, datetime.now(timezone.utc).isoformat()),
        )


def tank_history(key: str, limit: int = 30, db_path: str | None = None) -> list[tuple[str, float]]:
    """Recent (timestamp_iso, level) rows for a tank, oldest→newest."""
    try:
        with sqlite3.connect(db_path or LOGBOOK_DB_PATH) as conn:
            conn.execute(_TANK_DDL)
            rows = conn.execute(
                "SELECT timestamp, level FROM tank_readings WHERE tank = ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (key, limit),
            ).fetchall()
        return [(ts, lvl) for ts, lvl in reversed(rows)]
    except Exception as e:
        log.warning("tank_history(%s) failed (%s)", key, e)
        return []


def project_threshold(history: list[tuple[str, float]], direction: str) -> dict | None:
    """Linear-fit ETA to the critical level (100% for fill, 0% for drain).

    Returns {"eta": datetime(UTC), "days": float, "rate_pct_day": float}, or None
    when there are <2 readings or the trend runs the safe way / is flat.
    """
    if len(history) < 2:
        return None
    times = [datetime.fromisoformat(ts) for ts, _ in history]
    t0 = times[0]
    xs = [(t - t0).total_seconds() / 86400 for t in times]   # days
    ys = [lvl for _, lvl in history]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return None
    slope = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / denom  # %/day
    if (direction == "fill" and slope <= 0) or (direction == "drain" and slope >= 0):
        return None
    target = 100.0 if direction == "fill" else 0.0
    days = (target - ys[-1]) / slope
    if days <= 0:
        return None
    return {"eta": times[-1] + timedelta(days=days), "days": days, "rate_pct_day": slope}


def _sample_tank(spec: TankSpec) -> tuple[float, list[tuple[str, float]], dict | None]:
    """Synthetic last-7-days trend for the 'awaiting sensor' placeholder."""
    now = datetime.now(timezone.utc)
    current = 72.0 if spec.direction == "fill" else 38.0
    daily = 5.0 if spec.direction == "fill" else -6.0   # %/day toward the concern
    history = [
        ((now - timedelta(days=age)).isoformat(), max(0.0, min(100.0, current - daily * age)))
        for age in range(7, -1, -1)
    ]
    return current, history, project_threshold(history, spec.direction)


def _tank_color(direction: str, level: float) -> str:
    severity = level / 100 if direction == "fill" else 1 - level / 100
    if severity >= 0.85:
        return "#ef4444"
    if severity >= 0.6:
        return "#fbbf24"
    return "#5eead4"


def _fmt_date(dt: datetime) -> str:
    d = dt.astimezone()
    return f"{d.strftime('%b')} {d.day}"


def build_tank_panel(spec: TankSpec, level: float | None, history: list[tuple[str, float]],
                     projection: dict | None, placeholder: bool = False) -> str:
    """Inline SVG: a fill bar plus a framed mini-chart — last 7 days of history on
    the left, a 'now' marker at the centre, and a dashed projection to the FULL/
    EMPTY threshold on the right with an ETA date. Pure; "" when no level."""
    if level is None:
        return ""
    W, H = 720, 150
    color = _tank_color(spec.direction, level)
    parts = [
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
        f'class="tank" role="img" aria-label="{spec.label} {level:.0f} percent">'
    ]
    parts.append(f'<text x="0" y="14" fill="#94a3b8" font-size="12" letter-spacing="1.2">{spec.label.upper()}</text>')
    parts.append(f'<text x="{W}" y="15" fill="{color}" font-size="17" font-weight="700" text-anchor="end">{level:.0f}%</text>')
    # fill bar
    by, bh = 24, 18
    parts.append(f'<rect x="0" y="{by}" width="{W}" height="{bh}" rx="6" fill="#1e293b"/>')
    parts.append(f'<rect x="0" y="{by}" width="{max(3, W * level / 100):.1f}" height="{bh}" rx="6" fill="{color}"/>')
    # eta / action sentence
    if placeholder:
        sub = "sample · awaiting sensor"
    elif projection:
        when = "full" if spec.direction == "fill" else "empty"
        d = projection["days"]
        amount = "<1 day" if d < 1 else f"{round(d)} day{'s' if round(d) != 1 else ''}"
        sub = f"≈ {when} in {amount} · {spec.action}"
    else:
        sub = "collecting trend"
    parts.append(f'<text x="0" y="58" fill="{color}" font-size="13">{sub}</text>')

    # framed mini-chart: history (left) | now (centre) | projection (right)
    CL, CT, CB = 38, 72, 132
    cx = (CL + W) / 2
    target = 100.0 if spec.direction == "fill" else 0.0

    def CY(v: float) -> float:
        return CB - (CB - CT) * (v / 100)

    # frame + y reference (0% / 100%)
    parts.append(f'<line x1="{CL}" y1="{CY(100):.1f}" x2="{W}" y2="{CY(100):.1f}" stroke="#1e293b" stroke-width="1"/>')
    parts.append(f'<line x1="{CL}" y1="{CY(0):.1f}" x2="{W}" y2="{CY(0):.1f}" stroke="#1e293b" stroke-width="1"/>')
    parts.append(f'<text x="{CL - 6}" y="{CY(100) + 4:.1f}" fill="#475569" font-size="10" text-anchor="end">100</text>')
    parts.append(f'<text x="{CL - 6}" y="{CY(0) + 4:.1f}" fill="#475569" font-size="10" text-anchor="end">0</text>')
    # threshold word at its line
    parts.append(f'<text x="{CL + 4}" y="{CY(target) + (12 if spec.direction == "fill" else -5):.1f}" fill="{color}" font-size="10" letter-spacing="1">{"FULL" if spec.direction == "fill" else "EMPTY"}</text>')
    # now marker (centre)
    parts.append(f'<line x1="{cx:.1f}" y1="{CT}" x2="{cx:.1f}" y2="{CB}" stroke="#334155" stroke-width="1" stroke-dasharray="3 3"/>')
    parts.append(f'<text x="{cx:.1f}" y="{CT - 3:.1f}" fill="#94a3b8" font-size="10" text-anchor="middle">now</text>')

    pts = [(datetime.fromisoformat(ts), lvl) for ts, lvl in history]
    if pts:
        cutoff = pts[-1][0] - timedelta(days=7)
        pts7 = [p for p in pts if p[0] >= cutoff] or pts
        t_start, t_now = pts7[0][0], pts7[-1][0]
        tspan = (t_now - t_start).total_seconds() or 1.0

        def HX(t: datetime) -> float:
            return CL + (cx - CL) * ((t - t_start).total_seconds() / tspan)

        hline = " ".join(f"{HX(t):.1f},{CY(l):.1f}" for t, l in pts7)
        parts.append(f'<polyline points="{hline}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        parts.append(f'<circle cx="{cx:.1f}" cy="{CY(level):.1f}" r="3.5" fill="{color}"/>')
        # x labels: start date (left) and eta date (right)
        parts.append(f'<text x="{CL}" y="146" fill="#64748b" font-size="10">{_fmt_date(t_start)}</text>')
        if projection:
            parts.append(f'<line x1="{cx:.1f}" y1="{CY(level):.1f}" x2="{W}" y2="{CY(target):.1f}" stroke="{color}" stroke-width="1.8" stroke-dasharray="5 4" opacity="0.8"/>')
            parts.append(f'<circle cx="{W}" cy="{CY(target):.1f}" r="3.5" fill="{color}"/>')
            parts.append(f'<text x="{W}" y="146" fill="{color}" font-size="10" text-anchor="end">{_fmt_date(projection["eta"])}</text>')
    parts.append("</svg>")
    return "".join(parts)


def prune_empty(briefing: dict) -> dict:
    """Drop all-empty rows/notes a model may pad arrays with, so the HTML never
    renders blank table lines or empty bullets. Mutates and returns briefing."""
    def _nonempty(row: dict) -> bool:
        return isinstance(row, dict) and any(str(v).strip() for v in row.values())

    weather = briefing.get("weather", {})
    if isinstance(weather.get("rows"), list):
        weather["rows"] = [r for r in weather["rows"] if _nonempty(r)]
    nav = briefing.get("navigation", {})
    if isinstance(nav.get("tide_rows"), list):
        nav["tide_rows"] = [r for r in nav["tide_rows"] if _nonempty(r)]
    vessel = briefing.get("vessel_systems", {})
    if isinstance(vessel.get("notes"), list):
        vessel["notes"] = [n for n in vessel["notes"] if str(n).strip()]
    if isinstance(briefing.get("advisories"), list):
        briefing["advisories"] = [
            a for a in briefing["advisories"] if isinstance(a, dict) and str(a.get("text", "")).strip()
        ]
    return briefing


def render_html(briefing: dict, wind: dict | None = None, compass_svg: str = "",
                tide_svg: str = "", tank_panels: list[str] | None = None,
                vessel_name: str = "Naturali") -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    return env.get_template("briefing.html.j2").render(
        b=briefing, wind=wind, compass_svg=compass_svg, tide_svg=tide_svg,
        tank_panels=tank_panels or [], vessel_name=vessel_name,
    )


def render_markdown(briefing: dict) -> str:
    """Render deterministic markdown from the structured briefing (logbook archive)."""
    h = briefing.get("header", {})
    lines = [f"# Daily Briefing — {h.get('date', '')}".rstrip()]
    pos_dest = " · ".join(p for p in [h.get("position"), h.get("destination")] if p)
    if pos_dest:
        lines.append(pos_dest)

    weather = briefing.get("weather", {})
    lines.append("\n## Weather")
    rows = weather.get("rows") or []
    if rows:
        lines.append("| Source | Wind | Pressure |")
        lines.append("|--------|------|----------|")
        for r in rows:
            lines.append(f"| {r.get('source','')} | {r.get('wind','')} | {r.get('pressure','')} |")
    if weather.get("analysis"):
        lines.append(weather["analysis"])

    navigation = briefing.get("navigation", {})
    lines.append("\n## Navigation")
    tide_rows = navigation.get("tide_rows") or []
    if tide_rows:
        lines.append("| Type | Time | Height |")
        lines.append("|------|------|--------|")
        for t in tide_rows:
            lines.append(f"| {t.get('type','')} | {t.get('time','')} | {t.get('height','')} |")
    if navigation.get("analysis"):
        lines.append(navigation["analysis"])
    if navigation.get("departure"):
        lines.append(f"**Departure:** {navigation['departure']}")

    vessel = briefing.get("vessel_systems", {})
    lines.append("\n## Vessel Systems")
    for note in vessel.get("notes") or []:
        lines.append(f"- {note}")

    advisories = briefing.get("advisories") or []
    if advisories:
        lines.append("\n## Advisories")
        for a in advisories:
            lines.append(f"- [{a.get('level','info')}] {a.get('text','')}")

    return "\n".join(lines)


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
        # Exit non-zero so the bridge surfaces this instead of logging
        # "briefing complete" — a clean return here is a silent failure.
        log.error("Navigator returned no response — aborting")
        raise SystemExit(1)

    structured = prune_empty(response["briefing"])
    # Header fields are deterministic — set them ourselves rather than trusting the
    # model (the structured-output repair often leaves them blank or guesses).
    now = datetime.now()
    header = structured.setdefault("header", {})
    header["date"] = f"{now:%B} {now.day}"
    position = reverse_geocode(lat, lon) or (tides or {}).get("station_name")
    if position:
        header["position"] = position
    destination = fetch_destination()
    if destination:
        header["destination"] = destination
    else:
        header.pop("destination", None)  # no active route → omit, don't show a model guess
    tts_extract = response["tts_extract"]

    current_wind = fetch_current_wind(lat, lon)
    if current_wind:
        current_wind["cardinal"] = cardinal(current_wind["direction_deg"])
    tide_curve = fetch_tide_curve(lat, lon)
    compass_svg = (
        build_wind_compass(current_wind["direction_deg"], current_wind["speed_kn"])
        if current_wind else ""
    )
    tide_svg = build_tide_chart(tide_curve)

    tank_panels = []
    for spec in TANKS:
        try:
            level = fetch_tank_level(spec.key)
            placeholder = level is None
            if placeholder:
                level, hist, proj = _sample_tank(spec)
            else:
                record_tank_reading(spec.key, level)
                hist = tank_history(spec.key)
                proj = project_threshold(hist, spec.direction)
            tank_panels.append(build_tank_panel(spec, level, hist, proj, placeholder=placeholder))
        except Exception as e:
            log.warning("tank panel %s failed: %s", spec.key, e)

    html = render_html(structured, current_wind, compass_svg, tide_svg, tank_panels,
                       vessel_name=fetch_vessel_name())
    markdown = render_markdown(structured)

    html_ok = True
    try:
        publish_html(html)
    except Exception as e:
        log.error("publish_html failed: %s", e)
        html_ok = False

    try:
        publish_to_ha("generated")
    except Exception as e:
        log.error("publish_to_ha failed: %s", e)

    try:
        publish_tts(tts_extract)
    except Exception as e:
        log.error("publish_tts failed: %s", e)

    try:
        archive_to_logbook(markdown, LOGBOOK_DB_PATH, lat, lon)
    except Exception as e:
        log.error("archive_to_logbook failed: %s", e)

    if not html_ok:
        # The HTML is the dashboard's only source — if scp failed, the briefing
        # is effectively invisible. Exit non-zero so the bridge surfaces it
        # (it discards our stderr on a clean exit) instead of logging success.
        log.error("briefing HTML did not reach HA — dashboard will be stale")
        raise SystemExit(1)

    log.info("briefing complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
