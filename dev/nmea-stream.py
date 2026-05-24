#!/usr/bin/env python3
"""NMEA 0183 TCP stream server for local SignalK development.

Streams the same Boundary Pass scenario as mock-signalk.py, but as real NMEA
sentences over a TCP connection. SignalK connects to this as a data provider.

Usage:
    python dev/nmea-stream.py          # default port 10110
    python dev/nmea-stream.py 10110

Then in SignalK admin:
    Server → Data Connections → Add connection
    Type: TCP, Host: localhost, Port: 10110, Protocol: NMEA0183
"""

import math
import random
import socket
import socketserver
import sys
import threading
import time
from datetime import datetime, timezone

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 10110

# ---------------------------------------------------------------------------
# Scenario: Boundary Pass, heading SE toward Bedwell Harbour
# Matches mock-signalk.py so the two can be used interchangeably.
# ---------------------------------------------------------------------------
LAT   = 48.7621     # °N
LON   = -123.0520   # °W
SOG   = 3.1         # m/s → 6.03 kts
COG   = 135.0       # °T
HDG_T = 130.0       # °T
STW   = 3.0         # m/s → 5.83 kts
WIND_SPEED_T = 8.5  # m/s → 16.52 kts true
WIND_ANGLE_T = 315.0  # °T (NW)
DEPTH = 38.0        # m below keel
MAG_VAR = 16.0      # °E


def jitter(value: float, pct: float = 0.01) -> float:
    return value * (1 + random.uniform(-pct, pct))


def checksum(sentence: str) -> str:
    val = 0
    for c in sentence:
        val ^= ord(c)
    return f"{val:02X}"


def nmea(sentence: str) -> bytes:
    cs = checksum(sentence)
    return f"${sentence}*{cs}\r\n".encode()


def dd_to_dmm(degrees: float) -> tuple[str, str]:
    """Convert decimal degrees to NMEA DDmm.mmm format + hemisphere."""
    hemi_pos = ("N", "E")
    hemi_neg = ("S", "W")
    hemi = hemi_pos if degrees >= 0 else hemi_neg
    d = abs(degrees)
    deg = int(d)
    minutes = (d - deg) * 60
    return f"{deg:02d}{minutes:07.4f}", hemi[0] if degrees >= 0 else hemi[1]


def lon_dmm(degrees: float) -> tuple[str, str]:
    d = abs(degrees)
    deg = int(d)
    minutes = (d - deg) * 60
    hemi = "E" if degrees >= 0 else "W"
    return f"{deg:03d}{minutes:07.4f}", hemi


def sentences() -> list[bytes]:
    """Generate one cycle of NMEA sentences for the current timestamp."""
    now = datetime.now(timezone.utc)
    hhmmss = now.strftime("%H%M%S.00")
    ddmmyy = now.strftime("%d%m%y")

    # GPS noise: ±3m ≈ ±0.000027° lat, ±0.000038° lon at 48°N
    lat_j = LAT + random.uniform(-0.000027, 0.000027)
    lon_j = LON + random.uniform(-0.000038, 0.000038)
    sog_kts = jitter(SOG) * 1.94384
    cog_j   = jitter(COG, 0.005)
    hdg_t_j = jitter(HDG_T, 0.005)
    hdg_m_j = hdg_t_j - MAG_VAR
    stw_kts = jitter(STW) * 1.94384
    wind_spd_kts = jitter(WIND_SPEED_T) * 1.94384
    wind_angle_j = jitter(WIND_ANGLE_T, 0.01)
    depth_j = jitter(DEPTH, 0.02)

    lat_str, lat_hemi = dd_to_dmm(lat_j)
    lon_str, lon_hemi = lon_dmm(lon_j)

    mag_var_dir = "E" if MAG_VAR >= 0 else "W"
    mag_var_abs = abs(MAG_VAR)

    result = [
        # RMC: position, SOG, COG, date, mag variation
        nmea(
            f"GPRMC,{hhmmss},A,{lat_str},{lat_hemi},{lon_str},{lon_hemi},"
            f"{sog_kts:.2f},{cog_j:.1f},{ddmmyy},{mag_var_abs:.1f},{mag_var_dir},A"
        ),
        # GGA: position, fix quality, altitude
        nmea(
            f"GPGGA,{hhmmss},{lat_str},{lat_hemi},{lon_str},{lon_hemi},"
            f"1,08,1.0,0.0,M,0.0,M,,"
        ),
        # VTG: course and speed over ground
        nmea(
            f"GPVTG,{cog_j:.1f},T,{cog_j - MAG_VAR:.1f},M,"
            f"{sog_kts:.2f},N,{sog_kts * 1.852:.2f},K,A"
        ),
        # VHW: heading and speed through water (GP talker — WI/SD/II filtered by SignalK provider)
        nmea(
            f"GPVHW,{hdg_t_j:.1f},T,{hdg_m_j:.1f},M,"
            f"{stw_kts:.2f},N,{stw_kts * 1.852:.2f},K"
        ),
        # MWV: wind speed and angle, true
        nmea(f"GPMWV,{wind_angle_j:.1f},T,{wind_spd_kts:.2f},N,A"),
        # DBT: depth below transducer
        nmea(
            f"GPDBT,{depth_j * 3.28084:.1f},f,{depth_j:.1f},M,"
            f"{depth_j * 0.546807:.1f},F"
        ),
        # HDT: heading true
        nmea(f"GPHDT,{hdg_t_j:.1f},T"),
    ]
    return result


class NMEAHandler(socketserver.BaseRequestHandler):
    def handle(self):
        addr = self.client_address[0]
        print(f"  SignalK connected from {addr}")
        try:
            while True:
                for line in sentences():
                    self.request.sendall(line)
                    time.sleep(0.05)
                time.sleep(0.65)
        except (BrokenPipeError, ConnectionResetError):
            print(f"  SignalK disconnected from {addr}")


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    server = ThreadedTCPServer(("0.0.0.0", PORT), NMEAHandler)

    print(f"NMEA stream  →  tcp://localhost:{PORT}")
    print()
    print("  Scenario: Boundary Pass, motorsailing SE to Bedwell Harbour")
    print(f"  Position:  {LAT}°N  {abs(LON)}°W")
    print(f"  Wind:      ~16.5 kts NW true")
    print(f"  SOG:       ~6.0 kts   COG: 135°T")
    print(f"  Depth:     ~38m")
    print()
    print("  In SignalK admin:")
    print("    Server → Data Connections → Add connection")
    print(f"   Type: TCP  Host: localhost  Port: {PORT}  Protocol: NMEA0183")
    print()
    print("  Ctrl+C to stop")
    print()

    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
