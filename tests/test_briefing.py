import respx
import httpx
import pytest
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
