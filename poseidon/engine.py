"""poseidon/engine.py — the crew-channel turn engine (spec §2-§4).

One persistent SDK client = one conversation; turns serialize on a lock;
interim says derive from ToolUseBlocks; a watchdog emits "still working" at
20 s; the wall timeout interrupts the client and reports rc="timeout".
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable

from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

from poseidon import fallback, interim as interim_mod
from poseidon.reset import ResetPolicy

log = logging.getLogger(__name__)


@dataclass
class TurnResult:
    text: str
    rc: int | str            # 0 ok, 1 error, "timeout"
    dt_total: float
    dt_first_say: float | None


class CrewChannel:
    def __init__(self, *, client_factory: Callable[[], Awaitable],
                 reset_policy: ResetPolicy, timeout_s: float,
                 recall_fn: Callable[[str], list[str]] | None = None) -> None:
        self._factory = client_factory
        self._reset_policy = reset_policy
        self._timeout_s = timeout_s
        self._client = None
        self._last_turn_at: datetime | None = None
        self._lock = asyncio.Lock()
        self._rewarm_task: asyncio.Task | None = None
        if recall_fn is None:
            from poseidon.capability import recall_capabilities as recall_fn
        self._recall_fn = recall_fn

    async def warm(self) -> None:
        """Eagerly create the SDK client (spec §2: connect once at startup)
        so the first ask doesn't pay connect latency."""
        async with self._lock:
            if self._client is None:
                self._client = await self._factory()
                log.info("crew channel warmed")

    def _schedule_rewarm(self) -> None:
        """After a timeout/hard-error dispose, re-warm in the background.
        warm() takes the lock, so the task only runs once ask() releases it.
        Keep the task reference so it isn't garbage-collected mid-flight."""
        task = asyncio.get_running_loop().create_task(self.warm())
        task.add_done_callback(
            lambda t: (not t.cancelled() and t.exception()) and
            log.error("crew re-warm failed: %r", t.exception()))
        self._rewarm_task = task

    async def ask(self, text: str,
                  on_interim: Callable[[str], None]) -> TurnResult:
        """Run one crew turn. on_interim must not block (schedule, don't publish inline) \
— it is called synchronously from the consume loop."""
        async with self._lock:
            now = datetime.now().astimezone()
            if self._client is not None and \
                    self._reset_policy.should_reset(self._last_turn_at, now, text):
                log.info("conversation reset")
                await self._dispose()
            if self._client is None:
                self._client = await self._factory()

            policy = interim_mod.InterimPolicy()
            t0 = time.monotonic()
            dt_first_say: float | None = None
            texts: list[str] = []
            rc: int | str = 0

            def emit(phrase: str) -> None:
                nonlocal dt_first_say
                if dt_first_say is None:
                    dt_first_say = time.monotonic() - t0
                try:
                    on_interim(phrase)
                except Exception:  # a failed interim must never kill the turn
                    log.exception("interim say failed")

            async def watchdog() -> None:
                await asyncio.sleep(interim_mod.STILL_WORKING_AFTER_S)
                phrase = policy.still_working()
                if phrase:
                    emit(phrase)

            async def run_query(query_text: str) -> None:
                nonlocal rc
                texts.clear()
                await self._client.query(query_text)
                async for message in self._client.receive_response():
                    if isinstance(message, AssistantMessage):
                        tools = [b.name for b in message.content
                                 if isinstance(b, ToolUseBlock)]
                        if tools:
                            phrase = policy.note_tool_use(tools)
                            if phrase:
                                emit(phrase)
                        texts.extend(b.text for b in message.content
                                     if isinstance(b, TextBlock))
                    elif isinstance(message, ResultMessage):
                        rc = 1 if message.is_error else 0

            dog = asyncio.create_task(watchdog())
            try:
                await asyncio.wait_for(run_query(text), self._timeout_s)
                if rc == 0 and fallback.is_no_route(" ".join(texts).strip()):
                    try:
                        facts = await asyncio.to_thread(self._recall_fn, text)
                    except Exception:
                        log.warning("capability recall failed; no fallback route")
                        facts = []
                    retry = fallback.build_retry_prompt(text, facts)
                    if retry is not None:
                        # INTENTIONAL out-of-budget emit: RECONSIDER_PHRASE signals a
                        # retry transition, not tool progress — it is distinct from the
                        # still-working/tool-ack budget managed by InterimPolicy.
                        emit(interim_mod.RECONSIDER_PHRASE)
                        await asyncio.wait_for(run_query(retry), self._timeout_s)
                        if fallback.is_no_route(" ".join(texts).strip()):
                            texts[:] = [interim_mod.NO_HELP_PHRASE]
                    else:
                        # No capability facts to augment with — nothing to retry.
                        texts[:] = [interim_mod.NO_HELP_PHRASE]
            except asyncio.TimeoutError:
                rc = "timeout"
                texts.clear()
                with contextlib.suppress(Exception):
                    await self._client.interrupt()
                # The SDK's message stream is shared across turns; an
                # abandoned drain leaves stale messages queued (incl. the
                # interrupted turn's ResultMessage), desyncing later turns.
                # A timed-out conversation has little continuity value:
                # drop the client, next ask starts fresh.
                await self._dispose()
                self._schedule_rewarm()
            except Exception:
                log.exception("turn failed; disposing client")
                rc = 1
                texts.clear()
                await self._dispose()
                self._schedule_rewarm()
            finally:
                dog.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await dog

            self._last_turn_at = datetime.now().astimezone()
            return TurnResult(text=" ".join(texts).strip(), rc=rc,
                              dt_total=time.monotonic() - t0,
                              dt_first_say=dt_first_say)

    async def _dispose(self) -> None:
        if self._client is not None:
            with contextlib.suppress(Exception):
                await self._client.disconnect()
            self._client = None

    async def aclose(self) -> None:
        async with self._lock:
            await self._dispose()


async def sdk_client_factory():
    """Production factory: a connected ClaudeSDKClient on the crew options."""
    from claude_agent_sdk import ClaudeSDKClient

    from poseidon.profiles import crew_options

    # ClaudeSDKClient.__init__(self, options, transport=None) — connect() takes no args
    client = ClaudeSDKClient(options=crew_options())
    await client.connect()
    return client
