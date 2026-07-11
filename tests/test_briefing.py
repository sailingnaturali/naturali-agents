import math
import re

import respx
import httpx
import pytest
import sqlite3
import subprocess
import tempfile
import os
import importlib
import json
from pathlib import Path
import briefing


STRUCTURED = {
    "briefing": {
        "header": {"date": "May 30", "position": "Boundary Pass", "destination": "Ganges"},
        "weather": {"rows": [{"source": "Forecast", "wind": "5 kn N", "pressure": "1015 steady"}],
                    "analysis": "Settled."},
        "navigation": {"tide_rows": [{"type": "High", "time": "12:38", "height": "3.8 m"}],
                       "departure": "0900", "analysis": "Slack favours morning."},
        "vessel_systems": {"notes": ["Black water 72% — pump out at Ganges."]},
        "advisories": [{"level": "caution", "text": "Pressure falling — recheck in 1h."}],
    },
    "tts_extract": "Good morning. Light northerlies, settled.",
}


@respx.mock
def test_fetch_position_returns_lat_lon():
    respx.get(
        "http://localhost:8765/signalk/v1/api/vessels/self/navigation/position"
    ).mock(return_value=httpx.Response(
        200, json={"value": {"latitude": 48.76, "longitude": -123.05}}
    ))
    lat, lon = briefing.fetch_position()
    assert abs(lat - 48.76) < 0.001
    assert abs(lon - (-123.05)) < 0.001


@respx.mock
def test_fetch_position_falls_back_on_failure():
    respx.get(
        "http://localhost:8765/signalk/v1/api/vessels/self/navigation/position"
    ).mock(side_effect=httpx.ConnectError("refused"))
    lat, lon = briefing.fetch_position()
    assert lat == briefing.MOCK_LAT
    assert lon == briefing.MOCK_LON


def test_haversine_km_boundary_pass_to_tsawwassen():
    # Boundary Pass (48.76, -123.05) to Tsawwassen (49.007, -123.129) ≈ 28km
    d = briefing._haversine_km(48.76, -123.05, 49.007, -123.129)
    assert abs(d - 28.0) < 2.0


def test_nearest_tide_station_filters_operating_and_hilo():
    stations = [
        {
            "id": "aaa", "officialName": "No HiLo", "operating": True,
            "latitude": 49.0, "longitude": -123.0,
            "timeSeries": [{"code": "wlp"}],
        },
        {
            "id": "bbb", "officialName": "Not Operating", "operating": False,
            "latitude": 49.0, "longitude": -123.0,
            "timeSeries": [{"code": "wlp-hilo"}],
        },
        {
            "id": "ccc", "officialName": "Tsawwassen", "operating": True,
            "latitude": 49.007, "longitude": -123.129,
            "timeSeries": [{"code": "wlp-hilo"}],
        },
    ]
    result = briefing._nearest_tide_station(48.76, -123.05, stations)
    assert result["id"] == "ccc"


def test_classify_tide_events_alternates_high_low():
    raw = [
        {"eventDate": "2026-05-21T06:00:00Z", "value": 4.76},
        {"eventDate": "2026-05-21T11:39:00Z", "value": 3.38},
        {"eventDate": "2026-05-21T15:35:00Z", "value": 3.82},
        {"eventDate": "2026-05-21T23:11:00Z", "value": 0.58},
    ]
    result = briefing._classify_tide_events(raw)
    assert [e["type"] for e in result] == ["high", "low", "high", "low"]
    assert result[0]["height_m"] == 4.8
    assert result[0]["time_utc"] == "2026-05-21T06:00:00Z"


@respx.mock
def test_fetch_tides_returns_station_and_events():
    respx.get("https://api-sine.dfo-mpo.gc.ca/api/v1/stations").mock(
        return_value=httpx.Response(200, json=[
            {
                "id": "ccc", "officialName": "Tsawwassen", "operating": True,
                "latitude": 49.007, "longitude": -123.129,
                "timeSeries": [{"code": "wlp-hilo"}],
            }
        ])
    )
    respx.get("https://api-sine.dfo-mpo.gc.ca/api/v1/stations/ccc/data").mock(
        return_value=httpx.Response(200, json=[
            {"eventDate": "2026-05-21T06:00:00Z", "value": 4.76, "qcFlagCode": "1"},
            {"eventDate": "2026-05-21T11:39:00Z", "value": 3.38, "qcFlagCode": "1"},
            {"eventDate": "2026-05-21T15:35:00Z", "value": 3.82, "qcFlagCode": "1"},
            {"eventDate": "2026-05-21T23:11:00Z", "value": 0.58, "qcFlagCode": "1"},
        ])
    )
    result = briefing.fetch_tides(48.76, -123.05)
    assert result is not None
    assert result["station_name"] == "Tsawwassen"
    assert result["distance_km"] == 28
    assert len(result["events"]) == 4
    assert result["events"][0]["type"] == "high"


@respx.mock
def test_fetch_tides_returns_none_on_failure():
    respx.get("https://api-sine.dfo-mpo.gc.ca/api/v1/stations").mock(
        side_effect=httpx.ConnectError("refused")
    )
    assert briefing.fetch_tides(48.76, -123.05) is None


def test_build_prompt_contains_tides_and_weather_tool_instruction():
    tides = {
        "station_name": "Tsawwassen", "distance_km": 28,
        "events": [
            {"time_utc": "2026-05-21T06:00:00Z", "height_m": 4.8, "type": "high"},
            {"time_utc": "2026-05-21T11:39:00Z", "height_m": 3.4, "type": "low"},
        ],
    }
    prompt = briefing.build_prompt(tides, 48.76, -123.05)
    assert "Tsawwassen" in prompt
    assert "28km" in prompt
    # Position is now passed to the prompt so the navigator can call weather tools
    assert "48.7600" in prompt
    assert "-123.0500" in prompt
    # Navigator is instructed to fetch weather itself via the MCP tool
    assert "mcp_weather_get_marine_forecast" in prompt
    assert "briefing_markdown" not in prompt
    assert '"briefing"' in prompt
    assert "tts_extract" in prompt


def test_build_prompt_requests_structured_contract():
    prompt = briefing.build_prompt(None, 48.76, -123.05)
    assert "mcp_weather_get_marine_forecast" in prompt
    assert '"briefing"' in prompt
    assert "advisories" in prompt
    assert "briefing_markdown" not in prompt


def test_build_prompt_tides_unavailable():
    prompt = briefing.build_prompt(None, 48.76, -123.05)
    assert "unavailable" in prompt
    assert "mcp_weather_get_marine_forecast" in prompt


def test_is_response_line_filters_noise():
    assert briefing._is_response_line('{"briefing": {"header":{}}}') is True
    assert briefing._is_response_line("🔧 calling mcp_signalk_read_sensor") is False
    assert briefing._is_response_line("⚠ context limit approaching") is False
    assert briefing._is_response_line("session_id: abc123") is False
    assert briefing._is_response_line("") is False
    assert briefing._is_response_line("  ") is False


def test_parse_briefing_response_structured():
    import json as _j
    result = briefing.parse_briefing_response(_j.dumps(STRUCTURED))
    assert result is not None
    assert result["briefing"]["header"]["destination"] == "Ganges"
    assert result["tts_extract"].startswith("Good morning")


def test_parse_briefing_response_rejects_old_shape():
    text = '{"briefing_markdown": "## Weather", "tts_extract": "x"}'
    assert briefing.parse_briefing_response(text) is None


def test_parse_briefing_response_strips_code_fence_structured():
    import json as _j
    text = "```json\n" + _j.dumps(STRUCTURED) + "\n```"
    result = briefing.parse_briefing_response(text)
    assert result is not None and result["tts_extract"].startswith("Good morning")


def test_parse_briefing_response_with_preamble_noise():
    import json as _j
    text = (
        "🔧 calling mcp_signalk_read_sensor\n"
        "session_id: abc\n"
        + _j.dumps(STRUCTURED)
    )
    result = briefing.parse_briefing_response(text)
    assert result is not None
    assert result["tts_extract"].startswith("Good morning")


def test_parse_briefing_response_strips_pseudotag_preamble():
    # qwen2.5 occasionally prefixes the object with a stray pseudo-tag line.
    import json as _j
    text = "<no_preliminary nor_results_from_me>\n" + _j.dumps(STRUCTURED)
    result = briefing.parse_briefing_response(text)
    assert result is not None
    assert result["tts_extract"].startswith("Good morning")


def test_parse_briefing_response_invalid_returns_none():
    assert briefing.parse_briefing_response("not json at all") is None
    assert briefing.parse_briefing_response("") is None


def test_render_html_links_to_tides_webapp():
    html = briefing.render_html(STRUCTURED["briefing"],
                                tides_url="http://naturalaspi.local:3000/signalk-tides/")
    assert 'href="http://naturalaspi.local:3000/signalk-tides/"' in html
    assert "<svg" not in html or 'class="tide"' not in html


def test_render_html_omits_tides_link_when_no_url():
    html = briefing.render_html(STRUCTURED["briefing"])
    assert "signalk-tides" not in html


def test_build_wind_compass_renders_svg():
    svg = briefing.build_wind_compass(225.0, 12.0)
    assert svg.startswith("<svg")
    assert "</svg>" in svg


def test_build_wind_compass_missing_inputs_returns_empty_string():
    assert briefing.build_wind_compass(None, 12.0) == ""
    assert briefing.build_wind_compass(225.0, None) == ""


def test_build_wind_compass_arrow_clears_centre_speed():
    # The arrow shaft (the only stroke-width="4" line) must start well clear of
    # the centre numeral — its inner end was once at r*0.30 and collided with
    # the speed digits.
    svg = briefing.build_wind_compass(225.0, 7.0)
    m = re.search(
        r'<line x1="([\d.]+)" y1="([\d.]+)" [^>]*stroke-width="4"', svg
    )
    assert m, "arrow shaft line not found"
    x1, y1 = float(m.group(1)), float(m.group(2))
    dist = math.hypot(x1 - 80.0, y1 - 80.0)
    assert dist >= 28.0, f"arrow inner end {dist:.1f}px from centre overlaps the speed numeral"


def test_render_markdown_from_structured():
    md = briefing.render_markdown(STRUCTURED["briefing"])
    assert "## Weather" in md
    assert "## Navigation" in md
    assert "## Vessel Systems" in md
    assert "Ganges" in md            # header.destination
    assert "Pressure falling" in md  # advisory text


@respx.mock
def test_publish_to_ha_posts_to_rest_api(monkeypatch):
    monkeypatch.setenv("HOMEASSISTANT_TOKEN", "test-token")
    monkeypatch.setenv("HA_URL", "http://ha-test:8123")
    importlib.reload(briefing)

    respx.post("http://ha-test:8123/api/states/sensor.daily_briefing").mock(
        return_value=httpx.Response(200, json={"state": "generated"})
    )
    briefing.publish_to_ha("generated")
    assert respx.calls.last.request.url.path == "/api/states/sensor.daily_briefing"
    body = json.loads(respx.calls.last.request.content)
    assert body["state"] == "generated"
    # HTML now ships via scp to /config/www; the state sensor carries no content blob
    assert "content" not in body["attributes"]


def test_archive_briefing_inserts_row():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE marked_moments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                longitude REAL,
                latitude REAL
            )
        """)
        conn.commit()
        conn.close()

        briefing.archive_briefing("## Briefing text", db_path, 48.76, -123.05)

        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT text, latitude, longitude FROM marked_moments").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][0] == "## Briefing text"
        assert abs(rows[0][1] - 48.76) < 0.001
        assert abs(rows[0][2] - (-123.05)) < 0.001
    finally:
        os.unlink(db_path)


def test_dry_run_prints_prompt_without_calling_hermes():
    result = subprocess.run(
        ["uv", "run", "scripts/briefing.py", "--dry-run"],
        capture_output=True, text=True, timeout=60,
        cwd=str(Path(__file__).parent.parent),
    )
    assert result.returncode == 0
    assert "Generate the daily briefing" in result.stdout
    assert "TIDES" in result.stdout or "unavailable" in result.stdout
    # Navigator is now told to fetch weather itself via the MCP tool
    assert "mcp_weather_get_marine_forecast" in result.stdout
    assert '"briefing"' in result.stdout
    # hermes should NOT have been called (no 🔧 tool-call lines)
    assert "🔧" not in result.stdout


# ---------------------------------------------------------------------------
# Open-Meteo retry (fetch_current_wind / _get_with_retry)
# ---------------------------------------------------------------------------

WIND_JSON = {"current": {"wind_speed_10m": 9.2, "wind_direction_10m": 258.0}}


@respx.mock
def test_fetch_current_wind_retries_transient_502(monkeypatch):
    sleeps = []
    monkeypatch.setattr(briefing.time, "sleep", sleeps.append)
    route = respx.get("https://api.open-meteo.com/v1/forecast").mock(
        side_effect=[httpx.Response(502), httpx.Response(200, json=WIND_JSON)]
    )
    wind = briefing.fetch_current_wind(48.76, -123.05)
    assert wind == {"speed_kn": 9.2, "direction_deg": 258.0}
    assert route.call_count == 2
    assert sleeps == [1.0]


@respx.mock
def test_fetch_current_wind_gives_up_after_persistent_502(monkeypatch):
    sleeps = []
    monkeypatch.setattr(briefing.time, "sleep", sleeps.append)
    route = respx.get("https://api.open-meteo.com/v1/forecast").mock(
        return_value=httpx.Response(502)
    )
    assert briefing.fetch_current_wind(48.76, -123.05) is None
    assert route.call_count == 3
    assert sleeps == [1.0, 3.0]


@respx.mock
def test_fetch_current_wind_does_not_retry_4xx(monkeypatch):
    sleeps = []
    monkeypatch.setattr(briefing.time, "sleep", sleeps.append)
    route = respx.get("https://api.open-meteo.com/v1/forecast").mock(
        return_value=httpx.Response(400)
    )
    assert briefing.fetch_current_wind(48.76, -123.05) is None
    assert route.call_count == 1
    assert sleeps == []


@respx.mock
def test_fetch_current_wind_retries_transport_error(monkeypatch):
    sleeps = []
    monkeypatch.setattr(briefing.time, "sleep", sleeps.append)
    route = respx.get("https://api.open-meteo.com/v1/forecast").mock(
        side_effect=[httpx.ConnectError("reset"), httpx.Response(200, json=WIND_JSON)]
    )
    wind = briefing.fetch_current_wind(48.76, -123.05)
    assert wind == {"speed_kn": 9.2, "direction_deg": 258.0}
    assert route.call_count == 2
    assert sleeps == [1.0]


# ---------------------------------------------------------------------------
# SDK engine tests
# ---------------------------------------------------------------------------

import asyncio

from claude_agent_sdk import AssistantMessage, TextBlock


def _fake_query_yielding(*texts):
    async def fake(prompt, options):
        for t in texts:
            yield AssistantMessage(
                content=[TextBlock(text=t)], model="test-model"
            )
    return fake


def test_sdk_query_collects_assistant_text():
    fake = _fake_query_yielding("{\"briefing\":", " {}}")
    out = briefing._sdk_query("prompt", query_fn=fake)
    assert out == "{\"briefing\": {}}"


def test_sdk_query_returns_none_on_error():
    async def boom(prompt, options):
        raise RuntimeError("kaput")
        yield  # pragma: no cover — makes this an async generator
    assert briefing._sdk_query("prompt", query_fn=boom) is None


def test_sdk_query_modernizes_tool_names_in_prompt():
    seen = {}
    async def capture(prompt, options):
        seen["prompt"] = prompt
        yield AssistantMessage(content=[TextBlock(text="{}")], model="m")
    briefing._sdk_query("use mcp_weather_get_marine_forecast", query_fn=capture)
    assert "mcp__weather__get_marine_forecast" in seen["prompt"]


def test_briefing_options_scope():
    opts = briefing._briefing_options()
    assert set(opts.mcp_servers.keys()) <= {"signalk", "weather"}
    assert opts.allowed_tools == ["mcp__signalk", "mcp__weather"]
    assert opts.strict_mcp_config is True
    assert opts.max_turns > 1
