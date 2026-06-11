"""tests/test_poseidon_config.py"""
import os

from poseidon import config


def test_defaults():
    assert config.MODEL == "claude-sonnet-4-6"
    assert config.ASK_TIMEOUT_S == 60.0
    assert config.SAY_TOPIC == "naturali/agents/navigator/say"
    assert config.CLIENT_ID == "naturali-poseidon"


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
