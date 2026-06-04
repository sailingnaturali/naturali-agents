#!/usr/bin/env python3
"""NMEA 0183 log-file replay server for local SignalK development.

Drop-in companion to nmea-stream.py. Instead of generating the synthetic
Boundary Pass scenario, this streams a recorded NMEA 0183 log file over TCP,
looping forever. Use it when you want richer, *moving* passage data than the
single static synthetic point — e.g. the real Gulf of Finland passage in
plaka.log (changing wind, depth, speed, heading over 116K sentences).

Note: this replays NMEA *0183* sentence logs, not NMEA 2000 / canboat logs.
For true N2K PGN replay you need the `n2k-from-file` SignalK provider and a
canboat-format log (not staged in this repo yet).

Usage:
    python dev/nmea-replay.py                         # port 10110, default log
    python dev/nmea-replay.py 10110 /data/plaka.log   # explicit port + file
    NMEA_RATE=40 python dev/nmea-replay.py            # 40 sentences/sec

Then SignalK connects to it exactly like nmea-stream.py:
    Type: TCP  Host: <this host>  Port: 10110  Protocol: NMEA0183
"""

import os
import socketserver
import sys
import threading
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 10110
LOG_FILE = sys.argv[2] if len(sys.argv) > 2 else os.environ.get(
    "NMEA_LOG", "/data/plaka.log"
)
# Sentences per second. Real passage logs have no inter-line timing, so we pace
# them at a steady rate. ~20/s is lively but not a firehose; raise for faster
# loops, lower to feel closer to real time.
RATE = float(os.environ.get("NMEA_RATE", "20"))
DELAY = 1.0 / RATE if RATE > 0 else 0.0


def load_lines(path: str) -> list[bytes]:
    """Read the log once into memory as CRLF-terminated NMEA byte lines."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        out = []
        for raw in fh:
            line = raw.strip()
            if line:
                out.append((line + "\r\n").encode())
        return out


LINES = load_lines(LOG_FILE)


class ReplayHandler(socketserver.BaseRequestHandler):
    def handle(self):
        addr = self.client_address[0]
        print(f"  SignalK connected from {addr}")
        try:
            while True:
                for line in LINES:
                    self.request.sendall(line)
                    if DELAY:
                        time.sleep(DELAY)
        except (BrokenPipeError, ConnectionResetError):
            print(f"  SignalK disconnected from {addr}")


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    server = ThreadedTCPServer(("0.0.0.0", PORT), ReplayHandler)

    print(f"NMEA replay  →  tcp://localhost:{PORT}")
    print()
    print(f"  Log:    {LOG_FILE}")
    print(f"  Lines:  {len(LINES)}")
    print(f"  Rate:   {RATE:.0f} sentences/sec  (loop ≈ {len(LINES) / RATE / 60:.1f} min)")
    print()
    print("  In SignalK admin:")
    print("    Server → Data Connections → Add connection")
    print(f"    Type: TCP  Host: localhost  Port: {PORT}  Protocol: NMEA0183")
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
