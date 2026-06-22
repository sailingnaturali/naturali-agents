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


def test_timeout_disposes_client_so_next_turn_starts_fresh():
    scripts2 = [[_assistant([TextBlock(text="fresh")]), _result()]]
    pool = [[["HANG"]], scripts2]
    clients = []

    async def factory():
        c = FakeClient(pool.pop(0))
        clients.append(c)
        return c

    ch = CrewChannel(client_factory=factory, reset_policy=ResetPolicy(),
                     timeout_s=0.05)

    async def run():
        r1 = await ch.ask("slow", lambda s: None)
        ch._timeout_s = 60.0  # only the first ask should time out
        r2 = await ch.ask("quick", lambda s: None)
        return r1, r2

    r1, r2 = asyncio.run(run())
    assert r1.rc == "timeout"
    assert clients[0].interrupted and clients[0].disconnected
    assert len(clients) == 2 and r2.text == "fresh"


def test_warm_creates_client_and_ask_reuses_it():
    scripts = [[_assistant([TextBlock(text="hi")]), _result()]]
    ch, clients = make_channel(scripts)

    async def run():
        await ch.warm()
        await ch.warm()  # idempotent: second warm is a no-op
        return await ch.ask("q", lambda s: None)

    r = asyncio.run(run())
    assert len(clients) == 1   # factory called once; ask reused the warm client
    assert r.text == "hi"


def test_timeout_schedules_background_rewarm():
    pool = [[["HANG"]], [[]]]
    clients = []

    async def factory():
        c = FakeClient(pool.pop(0))
        clients.append(c)
        return c

    ch = CrewChannel(client_factory=factory, reset_policy=ResetPolicy(),
                     timeout_s=0.05)

    async def run():
        r = await ch.ask("slow", lambda s: None)
        for _ in range(10):           # let the scheduled warm task settle
            await asyncio.sleep(0)
        return r

    r = asyncio.run(run())
    assert r.rc == "timeout" and clients[0].disconnected
    assert len(clients) == 2 and ch._client is clients[1]   # re-warmed fresh


def test_consume_error_reports_rc1_and_disposes():
    class BrokenClient(FakeClient):
        async def receive_response(self):
            raise RuntimeError("CLI died")
            yield  # pragma: no cover

    clients = []

    async def factory():
        c = BrokenClient([[]])
        clients.append(c)
        return c

    ch = CrewChannel(client_factory=factory, reset_policy=ResetPolicy(),
                     timeout_s=1.0)
    r = asyncio.run(ch.ask("hi", lambda s: None))
    assert r.rc == 1 and r.text == ""
    assert clients[0].disconnected


def test_no_route_fallback_recalls_and_retries():
    """NO_ROUTE on first query → recall_fn called → retry → recovered answer."""
    no_route_msg = [
        _assistant([TextBlock(text="NO_ROUTE")]),
        _result(),
    ]
    recovered_msg = [
        _assistant([TextBlock(text="Drop the hook in Montague Harbour.")]),
        _result(),
    ]
    scripts = [no_route_msg, recovered_msg]

    recall_calls: list[str] = []

    def fake_recall(query: str) -> list[str]:
        recall_calls.append(query)
        return ["The Navigator handles where to anchor for the night."]

    clients = []

    async def factory():
        c = FakeClient(scripts)
        clients.append(c)
        return c

    ch = CrewChannel(client_factory=factory,
                     reset_policy=ResetPolicy(),
                     timeout_s=60.0,
                     recall_fn=fake_recall)

    r = asyncio.run(ch.ask("where can we tuck in tonight", lambda s: None))
    assert "Montague" in r.text
    assert recall_calls == ["where can we tuck in tonight"]
    assert len(clients[0].queries) == 2


def test_no_route_with_no_facts_emits_no_help_and_skips_retry():
    """NO_ROUTE + recall returns [] → NO_HELP phrase, exactly one query (no retry)."""
    no_route_msg = [
        _assistant([TextBlock(text="NO_ROUTE")]),
        _result(),
    ]
    scripts = [no_route_msg]

    def empty_recall(query: str) -> list[str]:
        return []

    clients = []

    async def factory():
        c = FakeClient(scripts)
        clients.append(c)
        return c

    from poseidon import interim as interim_mod

    ch = CrewChannel(client_factory=factory,
                     reset_policy=ResetPolicy(),
                     timeout_s=60.0,
                     recall_fn=empty_recall)

    r = asyncio.run(ch.ask("where to anchor?", lambda s: None))
    assert r.text == interim_mod.NO_HELP_PHRASE
    assert len(clients[0].queries) == 1


def test_normal_turn_never_calls_recall_fn():
    """A non-NO_ROUTE turn must never invoke recall_fn and sends exactly one query."""
    normal_msg = [
        _assistant([TextBlock(text="Wind is 10 knots from the NW.")]),
        _result(),
    ]
    scripts = [normal_msg]

    recall_called: list[str] = []

    def should_not_be_called(query: str) -> list[str]:
        recall_called.append(query)
        return []

    clients = []

    async def factory():
        c = FakeClient(scripts)
        clients.append(c)
        return c

    ch = CrewChannel(client_factory=factory,
                     reset_policy=ResetPolicy(),
                     timeout_s=60.0,
                     recall_fn=should_not_be_called)

    r = asyncio.run(ch.ask("wind?", lambda s: None))
    assert r.rc == 0
    assert "Wind" in r.text
    assert recall_called == [], "recall_fn must not be called on a normal turn"
    assert len(clients[0].queries) == 1
