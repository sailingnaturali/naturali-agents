#!/usr/bin/env bash
# Launched by com.naturali.mqtt-bridge launchd agent.
# Sources ~/.hermes/.env for MQTT credentials, then starts the bridge.
# Uses full paths because launchd runs with a minimal PATH.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${HOME}/.hermes/.env"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

cd "${SCRIPT_DIR}"

# Prevent duplicate instances. If a previous invocation is still alive (e.g.
# launchctl load was called while bootout was skipped), exit immediately so
# launchd's KeepAlive doesn't stack a second bridge on top of the first.
LOCK="/tmp/naturali-mqtt-bridge.pid"
if [[ -f "${LOCK}" ]] && kill -0 "$(cat "${LOCK}")" 2>/dev/null; then
  echo "bridge already running (PID $(cat "${LOCK}")), exiting duplicate."
  exit 0
fi
echo $$ > "${LOCK}"
trap 'rm -f "${LOCK}"' EXIT

# Retry loop so transient network failures (route not ready at boot) don't
# spin launchd's fast-respawn throttle. Backs off 10s between attempts.
until "${HOME}/.local/bin/uv" run mqtt_to_hermes.py; do
  echo "bridge exited, retrying in 10s..."
  sleep 10
done
