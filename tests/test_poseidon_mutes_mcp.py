# tests/test_poseidon_mutes_mcp.py
import asyncio

from poseidon import mutes_mcp


def test_server_exposes_only_set_alert_mute():
    tools = asyncio.run(mutes_mcp.mcp.list_tools())
    assert [t.name for t in tools] == ["set_alert_mute"]
    # spoken-surface guard: description mentions categories, not raw paths
    assert "whale" in tools[0].description.lower()


def test_tool_wires_publish_to_mqtt_helpers(monkeypatch):
    sent = []
    monkeypatch.setattr("poseidon.mute_publish.publish_mute_set",
                        lambda cat, env: sent.append(("set", cat, env)))
    monkeypatch.setattr("poseidon.mute_publish.publish_mute_clear",
                        lambda cat: sent.append(("clear", cat)))
    msg = mutes_mcp.set_alert_mute("whale-zones", "mute")
    assert sent and sent[0][0] == "set" and sent[0][1] == "whale-zones"
    assert "muted" in msg.lower()
    sent.clear()
    msg = mutes_mcp.set_alert_mute("whale-zones", "unmute")
    assert sent == [("clear", "whale-zones")]
    assert "back on" in msg.lower()
