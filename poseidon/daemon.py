"""poseidon/daemon.py — MQTT lanes -> crew channel / alarm lane / briefing.

MQTT discipline ported from the bridge: stable client id + clean_session=False.
QoS-1 + persistent session replays asks that arrive while the daemon is DOWN;
an ask already mid-processing when the daemon dies is PUBACK'd and lost (paho
acks on callback return). Adopting manual_ack is the recorded follow-up.
paho callbacks run on its network thread; work is handed to the asyncio loop
via run_coroutine_threadsafe.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import re
import shutil
import subprocess
import time
from typing import Callable

import paho.mqtt.client as mqtt
import paho.mqtt.publish as mqtt_publish

from poseidon import config, prompts, timing
from poseidon.alarms import AlarmLane
from poseidon.engine import CrewChannel, sdk_client_factory
from poseidon.mutes import MuteRegistry, parse_mute_envelope
from poseidon.reset import ResetPolicy

log = logging.getLogger(__name__)

UV = shutil.which("uv") or os.path.expanduser("~/.local/bin/uv")
CAFFEINATE = shutil.which("caffeinate") or "/usr/bin/caffeinate"


def decode_payload(raw: bytes) -> dict:
    try:
        obj = json.loads(raw.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"text": raw.decode(errors="replace")}
    return obj if isinstance(obj, dict) else {"text": str(obj)}


_MD_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_MD_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_MD_CODE = re.compile(r"`([^`\n]*)`")
_MD_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_MD_BULLET = re.compile(r"^- ", re.MULTILINE)
_MD_BLANKS = re.compile(r"\n{3,}")
_MD_TABLE_RULE = re.compile(r"^\|?[-:| ]+\|?$", re.MULTILINE)
# TTS reads abbreviations literally ("13 kn" -> "thirteen kay-en");
# normalize the marine units the model still abbreviates despite the
# prompt rule. Number-adjacent only, so prose words are never touched.
_UNIT_KN = re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:kn|kts|kt)\b")
_UNIT_NM = re.compile(r"\b(\d+(?:\.\d+)?)\s*nm\b")
_DEG_T = re.compile(r"\u00b0\s*T\b")
_DEG_M = re.compile(r"\u00b0\s*M\b")
_DEG = re.compile(r"\u00b0")


def _strip_markdown(text: str) -> str:
    """Says are spoken by TTS — drop markdown markers, keep the content."""
    text = _MD_BOLD.sub(r"\1", text)
    text = _MD_ITALIC.sub(r"\1", text)
    text = _MD_CODE.sub(r"\1", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_BULLET.sub("", text)
    text = _MD_TABLE_RULE.sub("", text)
    text = text.replace(" | ", ", ").replace("|", ",")
    return _MD_BLANKS.sub("\n\n", text)


def _normalize_speech(text: str) -> str:
    """Unit abbreviations -> spoken words (deterministic, number-adjacent)."""
    text = _UNIT_KN.sub(r"\1 knots", text)
    text = _UNIT_NM.sub(r"\1 nautical miles", text)
    text = _DEG_T.sub(" degrees true", text)
    text = _DEG_M.sub(" degrees magnetic", text)
    return _DEG.sub(" degrees", text)


def publish_say(text: str, trace_id: str | None = None,
                interim: bool = False) -> None:
    """Blocking publish (call via to_thread from the loop).

    interim=True marks mid-turn acknowledgments: HA's broadcast automation
    must NOT announce them — an assist_satellite.announce during the puck's
    active voice session kills the session, so the pipeline's final answer
    is never spoken (found live 2026-06-11). Interim-on-puck is parked until
    a satellite-safe mechanism exists; the flag keeps the payload contract
    ready for it.
    """
    auth = ({"username": config.MQTT_USER, "password": config.MQTT_PASSWORD}
            if config.MQTT_USER else None)
    say: dict = {"agent": config.AGENT_NAME,
                 "text": _normalize_speech(_strip_markdown(text))}
    if trace_id:
        say["trace_id"] = trace_id
    if interim:
        say["interim"] = True
    mqtt_publish.single(config.SAY_TOPIC, payload=json.dumps(say),
                        hostname=config.BROKER, port=config.PORT, auth=auth)


def publish_mute_clear(category: str) -> None:
    """Delete a retained mute slot (empty retained payload)."""
    auth = ({"username": config.MQTT_USER, "password": config.MQTT_PASSWORD}
            if config.MQTT_USER else None)
    mqtt_publish.single(f"{config.MUTES_TOPIC_PREFIX}/{category}", payload=None,
                        retain=True, hostname=config.BROKER, port=config.PORT,
                        auth=auth)


def publish_mute_set(category: str, envelope: dict) -> None:
    """Publish a retained mute envelope."""
    auth = ({"username": config.MQTT_USER, "password": config.MQTT_PASSWORD}
            if config.MQTT_USER else None)
    mqtt_publish.single(f"{config.MUTES_TOPIC_PREFIX}/{category}",
                        payload=json.dumps(envelope), retain=True,
                        hostname=config.BROKER, port=config.PORT, auth=auth)


def run_briefing(timing_ctx: dict | None = None) -> None:
    """Ported from the bridge: briefing.py handles its own outputs."""
    log.info("triggering daily briefing generation")
    scripts_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "scripts")
    t0 = time.monotonic()
    rc: int | str
    try:
        result = subprocess.run(
            [CAFFEINATE, "-i", "-s", UV, "run",
             os.path.join(scripts_dir, "briefing.py")],
            timeout=300, capture_output=True, text=True)
        rc = result.returncode
        if rc != 0:
            log.error("briefing.py failed (rc=%d): %s", rc, result.stderr.strip())
        else:
            log.info("briefing complete")
    except subprocess.TimeoutExpired:
        log.error("briefing.py timed out after 300s")
        rc = "timeout"
    if timing_ctx is not None:
        timing.append_timing_record(timing.build_record(
            timing_ctx["kind"], timing_ctx["trace_id"], timing_ctx["ts"],
            t_ha=timing_ctx["t_ha"], t_receive_wall=timing_ctx["t_wall"],
            dt_subprocess=time.monotonic() - t0, rc=rc))


class Poseidon:
    """Topic routing + say/timing plumbing; transport-agnostic for tests."""

    def __init__(self, *, channel: CrewChannel, alarm_lane: AlarmLane,
                 publish_say: Callable[..., None],
                 run_briefing: Callable[[dict | None], None],
                 mutes: MuteRegistry | None = None) -> None:
        self._channel = channel
        self._alarms = alarm_lane
        self._publish = publish_say
        self._briefing = run_briefing
        self._mutes = mutes or MuteRegistry()

    async def dispatch(self, topic: str, payload: dict, retain: bool = False) -> None:
        if topic.startswith("naturali/alerts/"):
            await self._handle_alert(payload, retain)
        elif topic.startswith(config.MUTES_TOPIC_PREFIX + "/"):
            self.handle_mute(topic, payload)
        elif topic == "naturali/intents/ask":
            await self._handle_ask(payload)
        elif topic == "naturali/intents/briefing":
            await asyncio.to_thread(self._briefing,
                                    timing.timing_ctx("briefing", payload))
        elif topic == "naturali/intents/mute":
            from datetime import datetime
            from poseidon.mutes import apply_mute_request

            def _pub(category, env):
                publish_mute_set(category, env) if env is not None else publish_mute_clear(category)
            apply_mute_request(payload.get("category", ""), payload.get("action", ""),
                               _pub, datetime.now().astimezone(), config.ROLLOVER_HOUR)
        else:
            log.warning("unhandled topic: %s", topic)

    async def _handle_ask(self, payload: dict) -> None:
        text = (payload.get("text") or "").strip()
        if not text:
            return
        ctx = timing.timing_ctx("ask", payload)
        trace_id = payload.get("trace_id") or None
        loop = asyncio.get_running_loop()
        interim_tasks: list[asyncio.Task] = []

        def on_interim(phrase: str) -> None:
            # interim says carry NO trace_id and interim=true; HA skips
            # them entirely for now (announce kills the puck session, and the
            # ask-roundtrip wait must only match the final say). Fire-and-
            # forget, but keep the task ref so it isn't GC'd mid-flight.
            interim_tasks.append(
                loop.create_task(asyncio.to_thread(
                    self._publish, phrase, None, True)))  # interim=True

        result = await self._channel.ask(text, on_interim)
        if interim_tasks:
            await asyncio.gather(*interim_tasks, return_exceptions=True)
        dt_publish = None
        final_text = None
        if result.rc == 0 and result.text:
            log.info("answer: %s", result.text)
            final_text = result.text
        elif result.rc == 1:
            # spec §6: hard failures publish a failure say so HA's waiting
            # intent resolves instead of dangling to the 75 s fallback.
            # Timeouts stay silent: HA's own fallback phrase covers those.
            log.warning("ask failed (rc=1); publishing failure say")
            final_text = "Sorry Captain, something went wrong answering that."
        if final_text is not None:
            t_pub = time.monotonic()
            await asyncio.to_thread(self._publish, final_text, trace_id)
            dt_publish = time.monotonic() - t_pub
        timing.append_timing_record(timing.build_record(
            ctx["kind"], ctx["trace_id"], ctx["ts"],
            t_ha=ctx["t_ha"], t_receive_wall=ctx["t_wall"],
            dt_hermes=result.dt_total,       # field name kept for report compat
            dt_first_say=result.dt_first_say,
            dt_publish=dt_publish,
            dt_total=time.monotonic() - ctx["t_mono"],
            query_chars=len(text), response_chars=len(result.text),
            rc=result.rc, model=config.MODEL))

    async def _handle_alert(self, payload: dict, retain: bool = False) -> None:
        ctx = timing.timing_ctx("alert", payload)
        t0 = time.monotonic()
        narration = await self._alarms.handle(payload, retain=retain)
        if narration:
            await asyncio.to_thread(self._publish, narration)
            timing.append_timing_record(timing.build_record(
                ctx["kind"], ctx["trace_id"], ctx["ts"],
                t_ha=ctx["t_ha"], t_receive_wall=ctx["t_wall"],
                dt_hermes=time.monotonic() - t0,
                dt_total=time.monotonic() - ctx["t_mono"],
                query_chars=0,
                response_chars=len(narration),
                rc=0,
                model=prompts.model_for_state(payload.get("state")) or config.MODEL))

    def handle_mute(self, topic: str, payload: dict) -> None:
        category = topic.rsplit("/", 1)[-1]
        envelope = parse_mute_envelope(payload) if payload else None
        self._mutes.apply(category, envelope)
        for expired in self._mutes.expired_categories():
            publish_mute_clear(expired)
            self._mutes.apply(expired, None)
            log.info("cleared expired mute slot: %s", expired)
        log.info("mute %s: %s", category, "set" if envelope else "cleared")


async def run() -> None:
    config.load_env_file(config.ENV_FILE)
    importlib.reload(config)   # constants freeze at import; re-read with env applied
    if not os.environ.get("LOGBOOK_SK_TOKEN"):
        log.warning("LOGBOOK_SK_TOKEN not in environment - logbook MCP writes will fail")
    channel = CrewChannel(client_factory=sdk_client_factory,
                          reset_policy=ResetPolicy(
                              idle_seconds=config.IDLE_RESET_S,
                              rollover_hour=config.ROLLOVER_HOUR),
                          timeout_s=config.ASK_TIMEOUT_S)
    mute_registry = MuteRegistry()
    app = Poseidon(
        channel=channel,
        alarm_lane=AlarmLane(is_muted=mute_registry.is_muted),
        publish_say=publish_say,
        run_briefing=run_briefing,
        mutes=mute_registry,
    )
    loop = asyncio.get_running_loop()
    # eager warm-up (spec §2 "connect once at startup"): the first ask should
    # not pay SDK connect latency. Keep the reference so the task survives.
    warm_task = loop.create_task(channel.warm())
    warm_task.add_done_callback(
        lambda f: (not f.cancelled() and f.exception()) and
        log.error("crew warm-up failed: %r", f.exception()))
    ask_queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            log.info("connected to %s:%d", config.BROKER, config.PORT)
            client.subscribe(config.INTENTS_TOPIC, qos=1)
            client.subscribe(config.ALERTS_TOPIC, qos=1)
            client.subscribe(config.MUTES_TOPIC, qos=1)
        else:
            log.error("connection failed rc=%s", rc)

    def on_message(client, userdata, msg):
        payload = decode_payload(msg.payload)
        log.info("intent: %s payload=%s", msg.topic, payload)
        if msg.topic == "naturali/intents/ask":
            # asks serialize through the queue (one crew turn at a time)
            loop.call_soon_threadsafe(ask_queue.put_nowait, (msg.topic, payload))
        else:
            # alarms + briefing run concurrently with any in-flight ask.
            # msg.retain marks the backlog the broker replays on (re)connect —
            # threaded through so the alarm lane reconciles it without speaking.
            fut = asyncio.run_coroutine_threadsafe(
                app.dispatch(msg.topic, payload, retain=msg.retain), loop)
            fut.add_done_callback(
                lambda f: f.exception() and
                log.error("lane dispatch failed: %r", f.exception()))

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id=config.CLIENT_ID, clean_session=False)
    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    if config.MQTT_USER:
        client.username_pw_set(config.MQTT_USER, config.MQTT_PASSWORD)
    client.connect(config.BROKER, config.PORT, keepalive=60)
    client.loop_start()

    log.info("poseidon up (model=%s)", config.MODEL)
    while True:
        topic, payload = await ask_queue.get()
        try:
            await app.dispatch(topic, payload)
        except Exception:
            log.exception("ask dispatch failed; daemon continues")
