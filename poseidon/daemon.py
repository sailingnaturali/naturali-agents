"""poseidon/daemon.py — MQTT lanes -> crew channel / alarm lane / briefing.

MQTT discipline ported from the bridge: stable client id + clean_session=False
so QoS-1 intents queue at the broker while we're down (verified by the
2026-06-10 bridge-down drill). paho callbacks run on its network thread; work
is handed to the asyncio loop via run_coroutine_threadsafe.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
from typing import Callable

import paho.mqtt.client as mqtt
import paho.mqtt.publish as mqtt_publish

from poseidon import config, timing
from poseidon.alarms import AlarmLane
from poseidon.engine import CrewChannel, sdk_client_factory
from poseidon.reset import ResetPolicy

log = logging.getLogger(__name__)

UV = shutil.which("uv") or os.path.expanduser("~/.local/bin/uv")
CAFFEINATE = shutil.which("caffeinate") or "/usr/bin/caffeinate"


def decode_payload(raw: bytes) -> dict:
    try:
        return json.loads(raw.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"text": raw.decode(errors="replace")}


def publish_say(text: str, trace_id: str | None = None) -> None:
    """Blocking publish (call via to_thread from the loop)."""
    auth = ({"username": config.MQTT_USER, "password": config.MQTT_PASSWORD}
            if config.MQTT_USER else None)
    say: dict = {"agent": config.AGENT_NAME, "text": text}
    if trace_id:
        say["trace_id"] = trace_id
    mqtt_publish.single(config.SAY_TOPIC, payload=json.dumps(say),
                        hostname=config.BROKER, port=config.PORT, auth=auth)


def run_briefing(timing_ctx: dict | None = None) -> None:
    """Ported from the bridge: briefing.py handles its own outputs."""
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
                 run_briefing: Callable[[dict | None], None]) -> None:
        self._channel = channel
        self._alarms = alarm_lane
        self._publish = publish_say
        self._briefing = run_briefing

    async def dispatch(self, topic: str, payload: dict) -> None:
        if topic.startswith("naturali/alerts/"):
            await self._handle_alert(payload)
        elif topic == "naturali/intents/ask":
            await self._handle_ask(payload)
        elif topic == "naturali/intents/briefing":
            await asyncio.to_thread(self._briefing,
                                    timing.timing_ctx("briefing", payload))
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
            # interim says carry NO trace_id -> HA broadcasts, never resolves
            # the waiting intent script (spec §4). Fire-and-forget, but keep
            # the task reference so it isn't garbage-collected mid-flight.
            interim_tasks.append(
                loop.create_task(asyncio.to_thread(self._publish, phrase)))

        result = await self._channel.ask(text, on_interim)
        if interim_tasks:
            await asyncio.gather(*interim_tasks, return_exceptions=True)
        dt_publish = None
        if result.rc == 0 and result.text:
            log.info("answer: %s", result.text)
            t_pub = time.monotonic()
            await asyncio.to_thread(self._publish, result.text, trace_id)
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

    async def _handle_alert(self, payload: dict) -> None:
        ctx = timing.timing_ctx("alert", payload)
        t0 = time.monotonic()
        narration = await self._alarms.handle(payload)
        if narration:
            await asyncio.to_thread(self._publish, narration)
        timing.append_timing_record(timing.build_record(
            ctx["kind"], ctx["trace_id"], ctx["ts"],
            t_ha=ctx["t_ha"], t_receive_wall=ctx["t_wall"],
            dt_hermes=time.monotonic() - t0,
            dt_total=time.monotonic() - ctx["t_mono"],
            query_chars=0,
            response_chars=len(narration or ""),
            rc=0 if narration else 1,
            model=None))


async def run() -> None:
    config.load_env_file(config.ENV_FILE)
    if not os.environ.get("LOGBOOK_SK_TOKEN"):
        log.warning("LOGBOOK_SK_TOKEN not in environment - logbook MCP writes will fail")
    app = Poseidon(
        channel=CrewChannel(client_factory=sdk_client_factory,
                            reset_policy=ResetPolicy(
                                idle_seconds=config.IDLE_RESET_S,
                                rollover_hour=config.ROLLOVER_HOUR),
                            timeout_s=config.ASK_TIMEOUT_S),
        alarm_lane=AlarmLane(),
        publish_say=publish_say,
        run_briefing=run_briefing,
    )
    loop = asyncio.get_running_loop()
    ask_queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            log.info("connected to %s:%d", config.BROKER, config.PORT)
            client.subscribe(config.INTENTS_TOPIC, qos=1)
            client.subscribe(config.ALERTS_TOPIC, qos=1)
        else:
            log.error("connection failed rc=%d", rc)

    def on_message(client, userdata, msg):
        payload = decode_payload(msg.payload)
        log.info("intent: %s payload=%s", msg.topic, payload)
        if msg.topic == "naturali/intents/ask":
            # asks serialize through the queue (one crew turn at a time)
            loop.call_soon_threadsafe(ask_queue.put_nowait, (msg.topic, payload))
        else:
            # alarms + briefing run concurrently with any in-flight ask
            asyncio.run_coroutine_threadsafe(
                app.dispatch(msg.topic, payload), loop)

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
        await app.dispatch(topic, payload)
