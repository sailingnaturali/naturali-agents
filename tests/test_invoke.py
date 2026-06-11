"""_invoke_hermes: early return on stdout quiet, honest rc on EOF, timeout kill.

These use real subprocesses — the early-return behavior (don't wait for the
child's teardown) can't be faked meaningfully.
"""
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "bridges"))

import mqtt_to_hermes as b


def test_returns_after_stdout_quiets_without_waiting_for_exit():
    cmd = [sys.executable, "-u", "-c",
           "import time; print('Captain. Wind is 12 knots.'); time.sleep(5)"]
    t0 = time.monotonic()
    out, rc = b._invoke_hermes(cmd, timeout=10, quiet_window=0.3)
    elapsed = time.monotonic() - t0
    assert "Wind is 12 knots" in out
    assert rc == 0
    assert elapsed < 3  # came back during the child's 5s "teardown" sleep


def test_eof_with_output_returns_zero():
    out, rc = b._invoke_hermes([sys.executable, "-c", "print('ok')"], timeout=5)
    assert out.strip() == "ok"
    assert rc == 0


def test_eof_without_output_returns_real_returncode():
    out, rc = b._invoke_hermes(
        [sys.executable, "-c", "import sys; sys.exit(3)"], timeout=5)
    assert out == ""
    assert rc == 3


def test_timeout_kills_and_raises():
    t0 = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        b._invoke_hermes(
            [sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.5)
    assert time.monotonic() - t0 < 3  # killed promptly, not after 10s
