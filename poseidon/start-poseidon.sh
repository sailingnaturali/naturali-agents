#!/usr/bin/env bash
# Launched by com.naturali.poseidon launchd agent.
# Sources POSEIDON_ENV (default ~/.poseidon/.env) for API keys + MQTT creds,
# then starts the Poseidon daemon.
# Uses full paths because launchd runs with a minimal PATH.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${POSEIDON_ENV:-${HOME}/.poseidon/.env}"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

# launchd starts us with a minimal PATH. Give the daemon — and every tool it
# spawns (uv in ~/.local/bin, the claude CLI for the agent SDK, caffeinate,
# node/npx via mise shims for MCP servers) — the same toolchain dirs an
# interactive shell has.  Without this, the claude-agent-sdk subprocess call
# fails with "claude not found on PATH".
export PATH="${HOME}/.local/bin:${HOME}/.local/share/mise/shims:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

cd "${REPO_DIR}"

# Prevent duplicate instances.  If a previous invocation is still alive (e.g.
# launchctl load was called while bootout was skipped), exit immediately so
# launchd's KeepAlive doesn't stack a second daemon on top of the first.
# Also verify the recorded PID actually belongs to our process — a recycled PID
# from an unrelated process must not keep poseidon down forever.
LOCK="/tmp/naturali-poseidon.pid"
if [[ -f "${LOCK}" ]]; then
  pid="$(cat "${LOCK}")"
  if kill -0 "$pid" 2>/dev/null && ps -p "$pid" -o command= 2>/dev/null | grep -q "start-poseidon\|python -m poseidon"; then
    echo "poseidon already running (pid $pid), exiting duplicate."
    exit 0
  fi
fi
echo $$ > "${LOCK}"
trap 'rm -f "${LOCK}"' EXIT

# Retry loop so transient network failures (broker not ready at boot, MCP
# server startup lag) don't spin launchd's fast-respawn throttle.
# Backs off 10s between attempts, matching the mqtt-bridge pattern.
until "${HOME}/.local/bin/uv" run python -m poseidon; do
  echo "poseidon exited, retrying in 10s..."
  sleep 10
done
