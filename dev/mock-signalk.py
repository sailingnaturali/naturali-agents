#!/usr/bin/env python3
"""Mock SignalK REST server for local development.

Returns realistic Gulf Islands / PNW passage data so signalk-mcp tools work
without a Pi or real instruments.

Usage:
    python dev/mock-signalk.py          # default port 8765
    python dev/mock-signalk.py 3000     # match real SignalK port

Then in another shell:
    export SIGNALK_URL=http://localhost:8765
    hermes chat -s naturali/navigator

Data scenario: s/v Naturali motorsailing SE through Boundary Pass,
approaching Bedwell Harbour on South Pender Island.
"""

import json
import math
import random
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def jitter(value: float, pct: float = 0.04) -> float:
    """Small random variation to simulate live sensor noise."""
    return round(value * (1 + random.uniform(-pct, pct)), 4)


# ---------------------------------------------------------------------------
# Scenario: Boundary Pass, heading SE toward Bedwell Harbour
# Position: ~48.76°N 123.05°W (mid-Boundary Pass)
# Wind: NW 8.5 m/s (~16.5 kts true)
# SOG: 3.1 m/s (~6 kts)  COG/HDG: ~135°T
# Battery: 68% SOC, 48V bank, -18A (motoring in light wind)
# ---------------------------------------------------------------------------

SCALARS = {
    # Navigation
    "navigation.speedOverGround":      3.1,     # m/s
    "navigation.courseOverGroundTrue": 2.356,   # radians (~135°T)
    "navigation.headingTrue":          2.268,   # radians (~130°T)
    "navigation.speedThroughWater":    3.0,     # m/s
    "navigation.magneticVariation":   -0.261,   # radians (~-15° E)
    # Wind (true)
    "environment.wind.speedTrue":      8.5,     # m/s (~16.5 kts)
    "environment.wind.angleTrueWater": 5.498,   # radians (~315° = NW)
    "environment.wind.speedApparent":  9.2,     # m/s
    # Depth
    "environment.depth.belowKeel":    38.0,     # m (deep water in the Pass)
}

POSITION = {"longitude": -123.0520, "latitude": 48.7621}

ACTIVE_ROUTE = {
    "href":      {"value": "/resources/routes/r-1"},
    "startTime": {"value": "2026-05-17T14:00:00Z"},
}

ROUTE_RESOURCE = {
    "name": "Victoria → Bedwell Harbour",
    "feature": {
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [-123.3656, 48.4284],  # Victoria Inner Harbour
                [-123.1800, 48.6100],  # Trial Island passage
                [-123.0520, 48.7621],  # Boundary Pass (current position)
                [-123.2299, 48.7554],  # Bedwell Harbour, S. Pender Island
            ],
        }
    },
}

BATTERY_HOUSE = {
    "stateOfCharge": 0.68,
    "voltage":       48.2,
    "current":      -18.0,
}


class SignalKHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")

        # Root API
        if path in ("/signalk", "/signalk/v1/api"):
            self._respond({"version": "2.0.0-mock", "vessels": {"self": {}}})
            return

        # Battery (nested response — must match before generic scalar handler)
        if path == "/signalk/v1/api/vessels/self/electrical/batteries/house":
            ts = now()
            self._respond({
                "capacity": {
                    "stateOfCharge": {
                        "value": jitter(BATTERY_HOUSE["stateOfCharge"], 0.01),
                        "timestamp": ts,
                    }
                },
                "voltage": {"value": jitter(BATTERY_HOUSE["voltage"], 0.005), "timestamp": ts},
                "current": {"value": jitter(BATTERY_HOUSE["current"], 0.08),  "timestamp": ts},
            })
            return

        # Active route
        if path == "/signalk/v1/api/vessels/self/navigation/courseGreatCircle/activeRoute":
            self._respond(ACTIVE_ROUTE)
            return

        # Route resource
        if path == "/signalk/v1/api/resources/routes/r-1":
            self._respond(ROUTE_RESOURCE)
            return

        # Position (structured value)
        if path == "/signalk/v1/api/vessels/self/navigation/position":
            self._respond({
                "value": {
                    "longitude": jitter(POSITION["longitude"], 0.0001),
                    "latitude":  jitter(POSITION["latitude"],  0.0001),
                },
                "timestamp": now(),
            })
            return

        # Generic scalar: /signalk/v1/api/vessels/self/{slash/path}
        prefix = "/signalk/v1/api/vessels/self/"
        if path.startswith(prefix):
            dot_path = path[len(prefix):].replace("/", ".")
            if dot_path in SCALARS:
                self._respond({"value": jitter(SCALARS[dot_path]), "timestamp": now()})
                return

        self.send_response(404)
        self.end_headers()

    def _respond(self, data: dict) -> None:
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        status = args[1] if len(args) > 1 else "?"
        print(f"  {status}  {self.path}")


def main() -> None:
    server = HTTPServer(("127.0.0.1", PORT), SignalKHandler)

    print(f"Mock SignalK  →  http://localhost:{PORT}")
    print()
    print("  Scenario: Boundary Pass, motorsailing SE to Bedwell Harbour")
    print(f"  Position:  {POSITION['latitude']}°N  {abs(POSITION['longitude'])}°W")
    print(f"  Wind:      ~16.5 kts NW true")
    print(f"  SOG:       ~6.0 kts   COG: 135°T")
    print(f"  Battery:   {int(BATTERY_HOUSE['stateOfCharge']*100)}% SOC  "
          f"{BATTERY_HOUSE['voltage']}V  {BATTERY_HOUSE['current']}A")
    print(f"  Route:     Victoria → Bedwell Harbour (4 waypoints)")
    print()
    print(f"  SIGNALK_URL=http://localhost:{PORT}")
    print("  Ctrl+C to stop")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
