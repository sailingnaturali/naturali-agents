#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27", "paho-mqtt>=2.0", "jinja2>=3.1"]
# ///
"""Daily briefing generator for s/v Naturali.

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
    '"vessel_systems": {"notes": ["Black water 72% — pump out at Sidney."]}, '
    '"advisories": [{"level": "info", "text": "Battery 68% — full range available."}]}, '
    '"tts_extract": "Good morning. Light westerlies, settled. Depart by 0900 for the flood."}'
)


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


def fetch_tide_curve(lat: float, lon: float) -> list[dict] | None:
    """Fetch the continuous (wlp) 15-min water-level series for the SVG tide curve.

    Uses the same nearest-station selection as fetch_tides so the curve matches
    the hi/lo table. Returns a list of {"time_utc", "height_m"} or None.
    """
    try:
        sr = httpx.get(CHS_STATIONS_URL, timeout=15)
        sr.raise_for_status()
        station = _nearest_tide_station(lat, lon, sr.json())

        today = datetime.now(timezone.utc).date()
        tomorrow = today + timedelta(days=1)
        dr = httpx.get(
            CHS_DATA_URL.format(station_id=station["id"]),
            params={
                "time-series-code": "wlp",
                "from": f"{today}T00:00:00Z",
                "to": f"{tomorrow}T00:00:00Z",
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


def fetch_wind_curve(lat: float, lon: float) -> list[dict] | None:
    """Fetch hourly wind speed (knots) for the SVG wind curve.

    Isolated chart-only fetch via Open-Meteo — weather *synthesis* still goes
    through the Navigator/weather-mcp. Returns [{"time", "knots"}] or None.
    """
    try:
        r = httpx.get(
            OPEN_METEO_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "hourly": "windspeed_10m",
                "wind_speed_unit": "kn",
                "forecast_days": 1,
                "timezone": "auto",
            },
            timeout=15,
        )
        r.raise_for_status()
        hourly = r.json()["hourly"]
        return [
            {"time": t, "knots": k}
            for t, k in zip(hourly["time"], hourly["windspeed_10m"])
        ]
    except Exception as e:
        log.warning("fetch_wind_curve failed: %s", e)
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


def build_svg_curve(
    wind: list[dict] | None,
    tide: list[dict] | None,
) -> str:
    """Render an inline SVG dual-curve (wind knots + tide metres) over the day.

    Pure function. Returns "" when there is nothing to draw. Each series is
    normalised to its own min/max so both fit the viewBox; a flat series is
    centred to avoid divide-by-zero.
    """
    if not wind and not tide:
        return ""

    W, H = 720, 200
    PAD = 24

    def _points(series: list[dict] | None, key: str) -> str:
        if not series:
            return ""
        vals = [pt[key] for pt in series]
        lo, hi = min(vals), max(vals)
        span = hi - lo
        n = len(series)
        coords = []
        for i, v in enumerate(vals):
            x = PAD + (W - 2 * PAD) * (i / (n - 1 if n > 1 else 1))
            if span == 0:
                y = H / 2
            else:
                y = PAD + (H - 2 * PAD) * (1 - (v - lo) / span)
            coords.append(f"{x:.1f},{y:.1f}")
        return " ".join(coords)

    parts = [
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
        f'class="curve" role="img" aria-label="Wind and tide over the day">'
    ]
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        x = PAD + (W - 2 * PAD) * frac
        parts.append(
            f'<line x1="{x:.1f}" y1="{PAD}" x2="{x:.1f}" y2="{H - PAD}" '
            f'stroke="#1e293b" stroke-width="1"/>'
        )

    tide_pts = _points(tide, "height_m")
    if tide_pts:
        parts.append(
            f'<polyline points="{tide_pts}" fill="none" stroke="#fbbf24" '
            f'stroke-width="2.5"/>'
        )
    wind_pts = _points(wind, "knots")
    if wind_pts:
        parts.append(
            f'<polyline points="{wind_pts}" fill="none" stroke="#5eead4" '
            f'stroke-width="2.5"/>'
        )

    parts.append(
        f'<text x="{PAD}" y="16" fill="#5eead4" font-size="12">wind kn</text>'
    )
    parts.append(
        f'<text x="{W - PAD - 48}" y="16" fill="#fbbf24" font-size="12">tide m</text>'
    )
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
    'JSON only' instruction, yet still produce the right *content*. Reformatting
    is a far easier task than synthesis, so a focused repair prompt usually
    complies. Runs on the same local model — no connectivity required.
    """
    log.info("Navigator response was not JSON — attempting JSON repair pass")
    repair_prompt = (
        "Convert the briefing below into ONE valid JSON object matching this "
        "exact shape. Output ONLY the JSON — no preamble, no markdown fences, "
        "no commentary. Use the real values from the text; if a field is "
        "missing, use a sensible empty value.\n\n"
        f"SHAPE:\n{SCHEMA_EXAMPLE}\n\n"
        f"BRIEFING TEXT:\n{prose.strip()}"
    )
    raw = _hermes_query(repair_prompt, timeout=90)
    if raw is None:
        return None
    repaired = parse_briefing_response(raw)
    if repaired is None:
        log.error("JSON repair pass also failed to produce valid JSON")
    return repaired


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


def render_html(briefing: dict, svg: str = "") -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    return env.get_template("briefing.html.j2").render(b=briefing, svg=svg)


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

    structured = response["briefing"]
    tts_extract = response["tts_extract"]

    wind = fetch_wind_curve(lat, lon)
    tide_curve = fetch_tide_curve(lat, lon)
    svg = build_svg_curve(wind, tide_curve)
    html = render_html(structured, svg)
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
