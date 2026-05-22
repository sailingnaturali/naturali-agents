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


@respx.mock
def test_fetch_weather_returns_dict():
    respx.get("https://api.open-meteo.com/v1/forecast").mock(
        return_value=httpx.Response(200, json={
            "hourly": {
                "time": [f"2026-05-21T{h:02d}:00" for h in range(24)],
                "windspeed_10m": [10.0] * 24,
                "winddirection_10m": [315.0] * 24,
                "windgusts_10m": [15.0] * 24,
                "pressure_msl": [1012.0] * 24,
            }
        })
    )
    respx.get("https://marine-api.open-meteo.com/v1/marine").mock(
        return_value=httpx.Response(200, json={
            "hourly": {
                "time": [f"2026-05-21T{h:02d}:00" for h in range(24)],
                "wave_height": [0.8] * 24,
            }
        })
    )
    result = briefing.fetch_weather(48.76, -123.05)
    assert result is not None
    assert result["wind_knots"] == 10.0
    assert result["wind_direction_deg"] == 315
    assert result["wind_gust_knots"] == 15.0
    assert result["pressure_hpa"] == 1012.0
    assert result["wave_height_m"] == 0.8


@respx.mock
def test_fetch_weather_returns_none_on_failure():
    respx.get("https://api.open-meteo.com/v1/forecast").mock(
        side_effect=httpx.ConnectError("refused")
    )
    result = briefing.fetch_weather(48.76, -123.05)
    assert result is None


@respx.mock
def test_fetch_weather_wave_height_optional():
    """Marine API failure should not fail the whole weather fetch."""
    respx.get("https://api.open-meteo.com/v1/forecast").mock(
        return_value=httpx.Response(200, json={
            "hourly": {
                "time": [f"2026-05-21T{h:02d}:00" for h in range(24)],
                "windspeed_10m": [10.0] * 24,
                "winddirection_10m": [315.0] * 24,
                "windgusts_10m": [15.0] * 24,
                "pressure_msl": [1012.0] * 24,
            }
        })
    )
    respx.get("https://marine-api.open-meteo.com/v1/marine").mock(
        side_effect=httpx.ConnectError("refused")
    )
    result = briefing.fetch_weather(48.76, -123.05)
    assert result is not None
    assert result["wave_height_m"] is None


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


def test_deg_to_compass():
    assert briefing._deg_to_compass(0) == "North"
    assert briefing._deg_to_compass(315) == "North-West"
    assert briefing._deg_to_compass(135) == "South-East"
    assert briefing._deg_to_compass(180) == "South"


def test_build_prompt_contains_weather_and_tides():
    weather = {
        "wind_knots": 14.0, "wind_direction_deg": 315, "wind_gust_knots": 19.0,
        "pressure_hpa": 1012.0, "pressure_trend": "steady",
        "afternoon_wind_knots": 18.0, "wave_height_m": 0.8,
    }
    tides = {
        "station_name": "Tsawwassen", "distance_km": 28,
        "events": [
            {"time_utc": "2026-05-21T06:00:00Z", "height_m": 4.8, "type": "high"},
            {"time_utc": "2026-05-21T11:39:00Z", "height_m": 3.4, "type": "low"},
        ],
    }
    prompt = briefing.build_prompt(weather, tides, 48.76, -123.05)
    assert "14.0 knots" in prompt
    assert "North-West" in prompt
    assert "1012.0 hPa" in prompt
    assert "Tsawwassen" in prompt
    assert "28km" in prompt
    assert "4.8m" in prompt
    assert "briefing_markdown" in prompt
    assert "tts_extract" in prompt


def test_build_prompt_weather_unavailable():
    prompt = briefing.build_prompt(None, None, 48.76, -123.05)
    assert "unavailable" in prompt
    assert "briefing_markdown" in prompt


def test_build_prompt_tides_unavailable():
    weather = {
        "wind_knots": 10.0, "wind_direction_deg": 270, "wind_gust_knots": 12.0,
        "pressure_hpa": 1010.0, "pressure_trend": "rising",
        "afternoon_wind_knots": 10.0, "wave_height_m": None,
    }
    prompt = briefing.build_prompt(weather, None, 48.76, -123.05)
    assert "10.0 knots" in prompt
    assert "unavailable" in prompt


def test_is_response_line_filters_noise():
    assert briefing._is_response_line('{"briefing_markdown": "test"}') is True
    assert briefing._is_response_line("🔧 calling mcp_signalk_read_sensor") is False
    assert briefing._is_response_line("⚠ context limit approaching") is False
    assert briefing._is_response_line("session_id: abc123") is False
    assert briefing._is_response_line("") is False
    assert briefing._is_response_line("  ") is False


def test_parse_briefing_response_clean_json():
    text = '{"briefing_markdown": "## Daily Briefing", "tts_extract": "Good morning."}'
    result = briefing.parse_briefing_response(text)
    assert result is not None
    assert result["briefing_markdown"] == "## Daily Briefing"
    assert result["tts_extract"] == "Good morning."


def test_parse_briefing_response_with_preamble_noise():
    text = (
        "🔧 calling mcp_signalk_read_sensor\n"
        "session_id: abc\n"
        '{"briefing_markdown": "## Briefing", "tts_extract": "Wind is 12 knots."}'
    )
    result = briefing.parse_briefing_response(text)
    assert result is not None
    assert result["tts_extract"] == "Wind is 12 knots."


def test_parse_briefing_response_multiline_json():
    text = '{\n  "briefing_markdown": "## B",\n  "tts_extract": "Good morning."\n}'
    result = briefing.parse_briefing_response(text)
    assert result is not None
    assert result["tts_extract"] == "Good morning."


def test_parse_briefing_response_invalid_returns_none():
    assert briefing.parse_briefing_response("not json at all") is None
    assert briefing.parse_briefing_response("") is None


def test_parse_briefing_response_strips_code_fence():
    text = (
        "```json\n"
        '{"briefing_markdown": "## Weather\\nAll clear.", "tts_extract": "Wind is 5 knots."}\n'
        "```"
    )
    result = briefing.parse_briefing_response(text)
    assert result is not None
    assert result["tts_extract"] == "Wind is 5 knots."
    assert result["briefing_markdown"] == "## Weather\nAll clear."


@respx.mock
def test_publish_to_ha_posts_to_rest_api(monkeypatch):
    monkeypatch.setenv("HOMEASSISTANT_TOKEN", "test-token")
    monkeypatch.setenv("HA_URL", "http://ha-test:8123")
    importlib.reload(briefing)

    respx.post("http://ha-test:8123/api/states/input_text.daily_briefing").mock(
        return_value=httpx.Response(200, json={"state": "ok"})
    )
    briefing.publish_to_ha("## Daily Briefing\nTest content")
    assert respx.calls.last.request.url.path == "/api/states/input_text.daily_briefing"
    body = json.loads(respx.calls.last.request.content)
    assert body["state"] == "## Daily Briefing\nTest content"


def test_archive_to_logbook_inserts_row():
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

        briefing.archive_to_logbook("## Briefing text", db_path, 48.76, -123.05)

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
    assert "WEATHER" in result.stdout or "unavailable" in result.stdout
    assert "TIDES" in result.stdout or "unavailable" in result.stdout
    # hermes should NOT have been called
    assert "mcp_signalk" not in result.stdout
