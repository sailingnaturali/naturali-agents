#!/usr/bin/env bash
# Shared: resolve the active vessel's name for prompt templating.
#
# Precedence:
#   1. $VESSEL_NAME, if set (explicit override)
#   2. the active vessel profile's name: (default sibling repo
#      ../infrastructure/vessels/profiles, override with $VESSEL_PROFILES_DIR)
#   3. "Naturali" (fallback)
#
# Usage:  source scripts/vessel-name.sh ; name="$(resolve_vessel_name "$repo_root")"
# Reads YAML with sed — no deps.
resolve_vessel_name() {
  local repo_root="${1:-$(pwd)}"
  if [ -n "${VESSEL_NAME:-}" ]; then printf '%s' "$VESSEL_NAME"; return; fi
  local profiles_dir="${VESSEL_PROFILES_DIR:-$repo_root/../infrastructure/vessels/profiles}"
  local active_file="$profiles_dir/active.yaml"
  if [ -f "$active_file" ]; then
    local active name_file name
    active="$(sed -n 's/^active:[[:space:]]*//p' "$active_file" | tr -d '"'\''[:space:]')"
    name_file="$profiles_dir/$active.yaml"
    if [ -n "$active" ] && [ -f "$name_file" ]; then
      name="$(sed -n 's/^name:[[:space:]]*//p' "$name_file" | head -1 | sed 's/^"\(.*\)"$/\1/; s/^'\''\(.*\)'\''$/\1/')"
      if [ -n "$name" ]; then printf '%s' "$name"; return; fi
    fi
  fi
  printf 'Naturali'
}
