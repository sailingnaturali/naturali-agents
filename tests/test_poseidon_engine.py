"""Crew-channel turn engine: serialization, interim says, timeout, reset."""
import asyncio

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

from poseidon.engine import CrewChannel
from poseidon.reset import ResetPolicy


def _assistant(blocks):
    return AssistantMessage(content=blocks, model="test")


def _result(is_error=False):
    # Installed SDK requires duration_api_ms (no default); stop_reason has a default.
    return ResultMessage(
        subtype="success" if not is_error else "error_during_execution",
        duration_ms=10,
        duration_api_ms=5,
        is_error=is_error,
        num_turns=1,
        session_id="s",
        stop_reason=None,
        total_cost_usd=0.0,
        usage=None,
        result="ok",
    )


class FakeClient:
    """Yields a scripted message sequence per query() call."""

    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.queries = []
        self.disconnected = False
        self.interrupted = False

    async def query(self, text):
        self.queries.append(text)

    async def receive_response(self):
        for msg in self.scripts.pop(0):
            if msg == "HANG":
                await asyncio.sleep(3600)
            yield msg

    async def interrupt(self):
        self.interrupted = True

    async def disconnect(self):
        self.disconnected = True


def make_channel(scripts, **kw):
    clients = []

    async def factory():
        c = FakeClient(scripts)
        clients.append(c)
        return c

    ch = CrewChannel(client_factory=factory,
                     reset_policy=kw.pop("reset_policy", ResetPolicy()),
                     timeout_s=kw.pop("timeout_s", 60.0))
    return ch, clients


def test_simple_turn_collects_text_and_no_interim():
    scripts = [[_assistant([TextBlock(text="Wind is 12 knots.")]), _result()]]
    ch, _ = make_channel(scripts)
    says = []
    r = asyncio.run(ch.ask("wind?", says.append))
    assert r.text == "Wind is 12 knots."
    assert r.rc == 0 and r.dt_first_say is None and says == []


def test_tool_use_emits_one_interim_say():
    scripts = [[
        _assistant([ToolUseBlock(id="1", name="mcp__pilotbook__search_anchorages",
                                 input={})]),
        _assistant([ToolUseBlock(id="2", name="mcp__weather__get_marine_forecast",
                                 input={})]),
        _assistant([TextBlock(text="Try Clam Bay.")]),
        _result(),
    ]]
    ch, _ = make_channel(scripts)
    says = []
    r = asyncio.run(ch.ask("anchor tonight?", says.append))
    assert says == ["Let me check the pilot book."]
    assert r.dt_first_say is not None and r.text == "Try Clam Bay."


def test_timeout_interrupts_and_reports():
    scripts = [["HANG"]]
    ch, clients = make_channel(scripts, timeout_s=0.05)
    r = asyncio.run(ch.ask("slow question", lambda s: None))
    assert r.rc == "timeout" and r.text == ""
    assert clients[0].interrupted


def test_reset_phrase_recreates_client():
    scripts1 = [[_assistant([TextBlock(text="a")]), _result()]]
    scripts2 = [[_assistant([TextBlock(text="b")]), _result()]]
    pool = [scripts1, scripts2]
    clients = []

    async def factory():
        c = FakeClient(pool.pop(0))
        clients.append(c)
        return c

    ch = CrewChannel(client_factory=factory, reset_policy=ResetPolicy(),
                     timeout_s=60.0)

    async def run():
        await ch.ask("first", lambda s: None)
        await ch.ask("ok new topic: second", lambda s: None)

    asyncio.run(run())
    assert len(clients) == 2 and clients[0].disconnected


def test_turns_are_serialized():
    order = []

    class SlowClient(FakeClient):
        async def receive_response(self):
            order.append("start")
            await asyncio.sleep(0.05)
            order.append("end")
            yield _assistant([TextBlock(text="x")])
            yield _result()

    async def factory():
        return SlowClient([[]])

    ch = CrewChannel(client_factory=factory, reset_policy=ResetPolicy(),
                     timeout_s=60.0)

    async def run():
        await asyncio.gather(ch.ask("a", lambda s: None),
                             ch.ask("b", lambda s: None))

    asyncio.run(run())
    assert order == ["start", "end", "start", "end"]
