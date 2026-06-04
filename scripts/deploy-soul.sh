#!/usr/bin/env bash
# Render the shared persona SOUL.md into the Hermes runtime, substituting
# {{VESSEL_NAME}} from the active vessel profile.
#
# Hermes loads ~/.hermes/SOUL.md as the BASE persona on every request (it is
# present even when no skill body is loaded), so it is the authoritative source
# of the vessel's identity and the always-on guardrails. It had been hand-placed
# once and gone stale — naming the wrong boat on every query. This gives it a
# real deploy step so it tracks the repo + active profile like the skill does.
#
# Usage: scripts/deploy-soul.sh
# Override the destination dir with HERMES_HOME (default: ~/.hermes).
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/vessel-name.sh
source "$repo_root/scripts/vessel-name.sh"

src="$repo_root/SOUL.md"
dest="${HERMES_HOME:-$HOME/.hermes}/SOUL.md"
[ -f "$src" ] || { echo "deploy-soul: missing $src" >&2; exit 1; }

vessel_name="$(resolve_vessel_name "$repo_root")"
mkdir -p "$(dirname "$dest")"
sed "s|{{VESSEL_NAME}}|$vessel_name|g" "$src" > "$dest"

echo "deploy-soul: wrote $dest (vessel: $vessel_name)"
