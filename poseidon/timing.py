"""poseidon/timing.py — voice-timing JSONL (same schema/path as the bridge).

Ported from bridges/mqtt_to_hermes.py (spec 2026-06-09-voice-latency-
instrumentation); adds the optional dt_first_say field (interim-say latency).
Instrumentation must never break the voice path: append warns-and-continues.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime

log = logging.getLogger(__name__)

TIMING_PATH = os.path.expanduser("~/Library/Logs/naturali/voice-timing.jsonl")


def _parse_t_ha(payload: dict) -> float | None:
    """Epoch-seconds stamp HA puts in intent payloads; None when absent/garbled.
    bool is an int subclass — reject it explicitly."""
    t = payload.get("t_ha")
    if isinstance(t, bool):
        return None
    return float(t) if isinstance(t, (int, float)) else None


def build_record(kind: str, trace_id: str, ts: str, *, t_ha: float | None,
                 t_receive_wall: float, **fields) -> dict:
    """One timing record. dt_transport crosses the HA↔Studio clock boundary —
    approximate, None when t_ha is absent, negative under skew (never clamped).
    Float fields are rounded to 3 decimals; ints/None/str pass through."""
    record: dict = {"trace_id": trace_id, "ts": ts, "kind": kind}
    record["dt_transport"] = (
        round(t_receive_wall - t_ha, 3) if t_ha is not None else None
    )
    for key, value in fields.items():
        record[key] = round(value, 3) if isinstance(value, float) else value
    return record


def append_timing_record(record: dict) -> None:
    """Append one JSONL line; instrumentation must never break the voice path."""
    try:
        os.makedirs(os.path.dirname(TIMING_PATH), exist_ok=True)
        with open(TIMING_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, allow_nan=False) + "\n")
    except (OSError, ValueError) as e:
        log.warning("timing record write failed: %s", e)


def timing_ctx(kind: str, payload: dict) -> dict:
    """Capture receive-time clocks for one dispatch."""
    return {
        "kind": kind,
        "trace_id": uuid.uuid4().hex[:6],
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "t_ha": _parse_t_ha(payload),
        "t_wall": time.time(),
        "t_mono": time.monotonic(),
    }
