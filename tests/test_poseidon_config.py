"""poseidon.config defaults and env-file loading."""
import importlib
import os

from poseidon import config


def test_defaults(monkeypatch):
    for var in ("POSEIDON_MODEL", "POSEIDON_ASK_TIMEOUT", "MQTT_CLIENT_ID",
                "AGENT_NAME", "MQTT_BROKER", "MQTT_PORT",
                "POSEIDON_IDLE_RESET", "POSEIDON_ROLLOVER_HOUR"):
        monkeypatch.delenv(var, raising=False)
    cfg = importlib.reload(config)
    assert cfg.MODEL == "claude-sonnet-4-6"
    assert cfg.ASK_TIMEOUT_S == 60.0
    assert cfg.SAY_TOPIC == "naturali/agents/navigator/say"
    assert cfg.CLIENT_ID == "naturali-poseidon"
    assert cfg.BROKER == "192.168.68.90" and cfg.PORT == 1883
    assert cfg.IDLE_RESET_S == 1800.0 and cfg.ROLLOVER_HOUR == 6


def test_load_env_file_sets_missing_only(tmp_path, monkeypatch):
    envfile = tmp_path / ".env"
    envfile.write_text(
        "# comment\nANTHROPIC_API_KEY=sk-test\nMQTT_PASSWORD=hunter2\n\nBROKEN\n"
    )
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("MQTT_PASSWORD", "already-set")
    config.load_env_file(str(envfile))
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-test"
    assert os.environ["MQTT_PASSWORD"] == "already-set"  # never overrides


def test_load_env_file_missing_path_is_noop(tmp_path):
    config.load_env_file(str(tmp_path / "nope"))  # must not raise


def test_load_env_file_strips_matching_outer_quotes(tmp_path, monkeypatch):
    envfile = tmp_path / ".env"
    envfile.write_text("A='single'\nB=\"double\"\nC='mismatched\"\n")
    for var in ("A", "B", "C"):
        monkeypatch.delenv(var, raising=False)
    config.load_env_file(str(envfile))
    assert os.environ["A"] == "single"
    assert os.environ["B"] == "double"
    assert os.environ["C"] == "'mismatched\""  # only matching pairs stripped
