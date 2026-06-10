#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["paho-mqtt>=2.0"]
# ///
"""Listen for HA voice intents on MQTT, dispatch to Hermes.

Run this as a persistent background service on the Mac Studio.
It subscribes to naturali/intents/# and maps each intent to a Hermes query.

Usage:
    uv run bridges/mqtt_to_hermes.py

Environment variables — see SPEC.md for the canonical table.

Intent topics → Hermes queries:
    naturali/intents/ask          →  "{text}"   (all voice — Hermes routes to the right tool)
    naturali/intents/briefing     →  runs briefing.py (handles its own outputs)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime

import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish

from _filter import is_response_line

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

def _find(name: str) -> str:
    """Resolve a command to its full path; falls back to ~/.local/bin/<name>."""
    return shutil.which(name) or os.path.expanduser(f"~/.local/bin/{name}")


UV = _find("uv")
HERMES = _find("hermes")
# The Mac sleeps overnight; run the briefing under caffeinate so the host stays
# awake for the whole run (otherwise it slogs across sleep cycles — ~10 min — and
# the subprocess's monotonic timeout never fires because monotonic pauses in sleep).
CAFFEINATE = shutil.which("caffeinate") or "/usr/bin/caffeinate"

BROKER = os.environ.get("MQTT_BROKER", "naturalaspi.local")
PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD")
AGENT_NAME = os.environ.get("AGENT_NAME", "navigator")
HERMES_SKILL = os.environ.get("HERMES_SKILL", "naturali/navigator")
SAY_TOPIC = f"naturali/agents/{AGENT_NAME}/say"
# Stable client id + a persistent session so the broker queues QoS-1 intents
# (e.g. the 0600 briefing) while the bridge is briefly disconnected, and
# delivers them on reconnect instead of dropping them.
CLIENT_ID = os.environ.get("MQTT_CLIENT_ID", "naturali-mqtt-bridge")
INTENTS_TOPIC = "naturali/intents/#"

# --- voice-timing instrumentation (spec: 2026-06-09-voice-latency-instrumentation) ---
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


def _timing_ctx(kind: str, payload: dict) -> dict:
    """Capture receive-time clocks for one dispatch."""
    return {
        "kind": kind,
        "trace_id": uuid.uuid4().hex[:6],
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "t_ha": _parse_t_ha(payload),
        "t_wall": time.time(),
        "t_mono": time.monotonic(),
    }


def _record_hermes(timing: dict | None, *, dt_hermes: float, rc, query: str,
                   response: str, dt_publish: float | None = None,
                   model: str | None = None) -> None:
    if timing is None:
        return
    append_timing_record(build_record(
        timing["kind"], timing["trace_id"], timing["ts"],
        t_ha=timing["t_ha"], t_receive_wall=timing["t_wall"],
        dt_hermes=dt_hermes,
        dt_publish=dt_publish,
        # receive → dispatch-end, so it carries µs of inter-measurement
        # overhead: hops won't sum exactly to dt_total.
        dt_total=time.monotonic() - timing["t_mono"],
        query_chars=len(query),
        response_chars=len(response),
        rc=rc,
        model=model,
    ))


# Severity-based model routing. emergency/alarm get the mature/cloud model
# (ALARM_MODEL); warn gets WARN_MODEL (empty -> Hermes config default; point it
# at the local model once that's running). See the agent-alarm-channel design.
_SEVERITY = {"nominal": 0, "normal": 1, "alert": 2, "warn": 3, "alarm": 4, "emergency": 5}


def model_for_state(state: str) -> str | None:
    """Model id for a severity, or None to use Hermes' configured default."""
    alarm_model = os.environ.get("ALARM_MODEL", "")
    warn_model = os.environ.get("WARN_MODEL", "")
    if _SEVERITY.get(state, 0) >= _SEVERITY["alarm"]:
        return alarm_model or None
    return warn_model or None


def alert_query(env: dict) -> str:
    """Seed a Hermes query from an alarm envelope.

    The response is spoken over TTS unprompted, so the seed demands a short
    announcement, not a situation report. Notification messages are built
    ready-to-speak at the source (e.g. signalk-dsc); raw coordinates and
    timestamps stay out of the seed so the model can't read them aloud.
    (2026-06-06: the old "gather wind, current, depth and position" seed had
    the puck reciting battery status after a DSC distress drill.)
    """
    return (
        f"ALARM DISPATCH ({env.get('state')}, path {env.get('path')}): "
        f'announce this to the Captain now: "{env.get("message")}". '
        "Speak at most two short sentences: the announcement, plus one action "
        "only if obvious and urgent. Do not report other systems or readings, "
        "and never speak coordinates, paths, MMSI numbers, or timestamps. "
        "Only if the quoted message is bare machine text may you call "
        "explain_notification(path, state) to phrase it better."
    )


def _run_hermes(query: str, model: str | None = None,
                timing: dict | None = None, trace_id: str | None = None) -> None:
    """Run a single Hermes query and pipe the response to MQTT TTS.

    trace_id, when present (asks from HA), is echoed into the say payload so
    HA's waiting intent script can match the reply. Unsolicited says (alarms,
    briefing) carry no trace_id — HA announces those on the puck instead.
    """
    log.info("hermes query: %s", query)
    cmd = [HERMES, "chat", "-Q", "-s", HERMES_SKILL, "-q", query]
    if model:
        cmd[2:2] = ["-m", model]  # insert after "chat"
    t0 = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        log.error("hermes timed out for query: %s", query)
        _record_hermes(timing, dt_hermes=time.monotonic() - t0, rc="timeout",
                       query=query, response="", model=model)
        return
    dt_hermes = time.monotonic() - t0

    if result.returncode != 0:
        log.error("hermes exit=%d stderr: %s", result.returncode, result.stderr.strip())
        _record_hermes(timing, dt_hermes=dt_hermes, rc=result.returncode,
                       query=query, response="", model=model)
        return

    lines = [l for l in result.stdout.splitlines() if is_response_line(l)]
    response = " ".join(lines).strip()
    dt_publish = None  # stays None when nothing was published
    if response:
        log.info("hermes response: %s", response)
        auth = {"username": MQTT_USER, "password": MQTT_PASSWORD} if MQTT_USER else None
        say: dict = {"agent": AGENT_NAME, "text": response}
        if trace_id:
            say["trace_id"] = trace_id
        t_pub = time.monotonic()
        publish.single(
            SAY_TOPIC,
            payload=json.dumps(say),
            hostname=BROKER,
            port=PORT,
            auth=auth,
        )
        dt_publish = time.monotonic() - t_pub
    _record_hermes(timing, dt_hermes=dt_hermes, rc=result.returncode, query=query,
                   response=response, dt_publish=dt_publish, model=model)


def _run_briefing(timing: dict | None = None) -> None:
    """Invoke briefing.py as a subprocess. It handles all publishing internally."""
    log.info("triggering daily briefing generation")
    scripts_dir = os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
    )
    briefing_script = os.path.join(scripts_dir, "briefing.py")
    t0 = time.monotonic()
    rc: int | str
    try:
        result = subprocess.run(
            [CAFFEINATE, "-i", "-s", UV, "run", briefing_script],
            timeout=300,  # synth + a possible JSON-repair pass = up to two model calls
            capture_output=True,
            text=True,
        )
        rc = result.returncode
        if result.returncode != 0:
            log.error("briefing.py failed (rc=%d): %s", result.returncode, result.stderr.strip())
        else:
            log.info("briefing complete")
    except subprocess.TimeoutExpired:
        log.error("briefing.py timed out after 300s")
        rc = "timeout"
    if timing is not None:
        append_timing_record(build_record(
            timing["kind"], timing["trace_id"], timing["ts"],
            t_ha=timing["t_ha"], t_receive_wall=timing["t_wall"],
            dt_subprocess=time.monotonic() - t0,
            rc=rc,
        ))


def on_connect(client: mqtt.Client, userdata: None, flags: dict, rc: int, properties=None) -> None:
    if rc == 0:
        log.info("connected to %s:%d", BROKER, PORT)
        # QoS 1 so the broker queues intents for our persistent session while
        # we're briefly offline (see CLIENT_ID / clean_session in main()).
        client.subscribe(INTENTS_TOPIC, qos=1)
        log.info("subscribed to %s (qos=1)", INTENTS_TOPIC)
        client.subscribe("naturali/alerts/#", qos=1)
        log.info("subscribed to naturali/alerts/# (qos=1)")
    else:
        log.error("connection failed, rc=%d", rc)


# Retained alerts redeliver on every reconnect; dedup by (path, timestamp) so a
# still-active alarm isn't re-dispatched each time we reconnect. Dispatch runs on
# a per-message daemon thread, so the check-then-act on _ALERT_SEEN is guarded by
# a lock (Hermes itself runs outside the lock — a slow subprocess must not
# serialize other alarms).
_ALERT_SEEN: dict[str, str] = {}
_ALERT_LOCK = threading.Lock()
_ACTIVE = {"warn", "alarm", "emergency"}


def handle_alert(env: dict, timing: dict | None = None) -> None:
    """Dispatch one alarm envelope to Hermes, deduped and severity-routed."""
    state = env.get("state")
    path = env.get("path", "")
    ts = env.get("timestamp")
    with _ALERT_LOCK:
        if state not in _ACTIVE:  # cleared or below-warn — ignore
            _ALERT_SEEN.pop(path, None)
            return
        if _ALERT_SEEN.get(path) == ts:
            return  # already handled this exact alarm
        _ALERT_SEEN[path] = ts
    _run_hermes(alert_query(env), model=model_for_state(state), timing=timing)


def _dispatch(topic: str, payload: dict) -> None:
    """Handle one message. Runs on a worker thread, not the MQTT loop."""
    if topic.startswith("naturali/alerts/"):
        handle_alert(payload, timing=_timing_ctx("alert", payload))
    elif topic == "naturali/intents/ask":
        text = payload.get("text", "").strip()
        if text:
            _run_hermes(text, timing=_timing_ctx("ask", payload),
                        trace_id=payload.get("trace_id") or None)
    elif topic == "naturali/intents/briefing":
        _run_briefing(timing=_timing_ctx("briefing", payload))
    else:
        log.warning("unhandled topic: %s", topic)


def on_message(client: mqtt.Client, userdata: None, msg: mqtt.MQTTMessage) -> None:
    topic = msg.topic
    try:
        payload = json.loads(msg.payload.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = {"text": msg.payload.decode(errors="replace")}

    log.info("intent: %s payload=%s", topic, payload)

    # Dispatch off the network loop so on_message returns immediately. A briefing
    # can take minutes; blocking here would stall keepalive (dropping the
    # connection) and delay the QoS-1 ack (triggering broker redelivery — i.e.
    # duplicate briefings). The worker thread does the slow work.
    threading.Thread(target=_dispatch, args=(topic, payload), daemon=True).start()


def main() -> None:
    # Fixed client id + clean_session=False → a persistent session the broker
    # keeps across our frequent reconnects, so QoS-1 intents published while
    # we're offline are queued and delivered on reconnect.
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=CLIENT_ID,
        clean_session=False,
    )
    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

    log.info("connecting to %s:%d as %s", BROKER, PORT, CLIENT_ID)
    client.connect(BROKER, PORT, keepalive=60)
    client.loop_forever()


if __name__ == "__main__":
    main()
