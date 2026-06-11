#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""hermes-ACP spike harness — ADR 0001 gate measurements.

Usage: uv run dev/acp_spike.py "What's the wind speed?" "What about the depth?"
Optional: ACP_SLEEP_BETWEEN=<seconds> sleeps between asks (gate 3 longevity).
Sends each ask as a session/prompt on ONE session, prints every session/update
notification with a monotonic timestamp, and reports per-ask wall times.
stderr from the hermes child goes to dev/acp_spike.stderr.log.
"""
import json
import os
import subprocess
import sys
import threading
import time

STDERR_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "acp_spike.stderr.log")

proc = subprocess.Popen(
    ["hermes", "acp"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    stderr=open(STDERR_LOG, "w"),
    text=True, bufsize=1,
)
_id = 0
_replies: dict[int, dict] = {}
_reply_evt = threading.Event()
T0 = time.monotonic()


def _send(obj: dict) -> None:
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()


def _reader():
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            print(f"[{time.monotonic()-T0:7.2f}s] non-JSON stdout: {line[:160]}")
            continue
        if "id" in msg and ("result" in msg or "error" in msg):
            _replies[msg["id"]] = msg
            _reply_evt.set()
        elif msg.get("method") == "session/update":
            upd = msg.get("params", {}).get("update", {})
            kind = upd.get("sessionUpdate") or upd.get("kind")
            print(f"[{time.monotonic()-T0:7.2f}s] update: {kind}: "
                  f"{json.dumps(upd)[:200]}")
        elif "method" in msg and "id" in msg:
            # Server->client request (e.g. permission ask). Auto-respond.
            print(f"[{time.monotonic()-T0:7.2f}s] server request: {msg['method']}: "
                  f"{json.dumps(msg.get('params', {}))[:160]}")
            if msg["method"] == "session/request_permission":
                opts = msg.get("params", {}).get("options", [])
                allow = next((o for o in opts
                              if o.get("kind", "").startswith("allow")), None)
                outcome = ({"outcome": "selected", "optionId": allow["optionId"]}
                           if allow else {"outcome": "cancelled"})
                _send({"jsonrpc": "2.0", "id": msg["id"],
                       "result": {"outcome": outcome}})
            else:
                _send({"jsonrpc": "2.0", "id": msg["id"], "result": {}})
        else:
            print(f"[{time.monotonic()-T0:7.2f}s] notif: {msg.get('method')}: "
                  f"{json.dumps(msg.get('params', {}))[:160]}")


threading.Thread(target=_reader, daemon=True).start()


def rpc(method: str, params: dict, timeout: float = 180.0) -> dict:
    global _id
    _id += 1
    req_id = _id
    _send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
    deadline = time.monotonic() + timeout
    while req_id not in _replies:
        if proc.poll() is not None:
            raise RuntimeError(f"{method}: hermes exited rc={proc.returncode}, "
                               f"see {STDERR_LOG}")
        if time.monotonic() > deadline:
            raise TimeoutError(method)
        _reply_evt.wait(0.5)
        _reply_evt.clear()
    reply = _replies.pop(req_id)
    if "error" in reply:
        raise RuntimeError(f"{method}: {reply['error']}")
    return reply["result"]


init = rpc("initialize", {"protocolVersion": 1, "clientCapabilities": {"fs": {}}})
print(f"[{time.monotonic()-T0:7.2f}s] initialize ->", json.dumps(init)[:300])
sess = rpc("session/new", {"cwd": os.getcwd(), "mcpServers": []})
session_id = sess["sessionId"]
print(f"[{time.monotonic()-T0:7.2f}s] session ->", session_id)

sleep_between = float(os.environ.get("ACP_SLEEP_BETWEEN", "0"))

for i, ask in enumerate(sys.argv[1:], 1):
    if i > 1 and sleep_between:
        print(f"--- sleeping {sleep_between:.0f}s before ask {i} (gate 3) ---")
        time.sleep(sleep_between)
    t = time.monotonic()
    result = rpc("session/prompt", {
        "sessionId": session_id,
        "prompt": [{"type": "text", "text": ask}],
    })
    print(f"=== ask {i} ({ask!r}): {time.monotonic()-t:.2f}s  "
          f"stop={result.get('stopReason')}")

proc.terminate()
