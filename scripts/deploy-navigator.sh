#!/usr/bin/env bash
# Assemble the Navigator skill from source fragments and deploy it to the
# Hermes runtime skills tree. Single source of truth lives in
# skills/navigator/ — this is the only thing that should write SKILL.md.
#
#   SKILL.md (runtime) = frontmatter.yaml (fenced) + body.md + briefing.md
#   prompts/navigator.md (repo doc) = body.md   (regenerated mirror)
#
# The source prompts are vessel-agnostic: the placeholder {{VESSEL_NAME}} is
# substituted with the active vessel's name when the runtime SKILL.md is
# written, so the agent calls the boat by its real name (and follows the
# active profile when you change boats — no prompt edits). Name resolution:
#   1. $VESSEL_NAME, if set (explicit override)
#   2. the active vessel profile's name: (default sibling repo
#      ../infrastructure/vessels/profiles, override with $VESSEL_PROFILES_DIR)
#   3. "Naturali" (fallback)
#
# The runtime skill is machine-local config (not committed). prompts/navigator.md
# IS committed and keeps the {{VESSEL_NAME}} placeholder — the documented prompt
# template can never drift from what runs.
#
# Usage: scripts/deploy-navigator.sh
# Override the destination with HERMES_SKILLS_DIR (default: ~/.hermes/skills).
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
src="$repo_root/skills/navigator"
skills_dir="${HERMES_SKILLS_DIR:-$HOME/.hermes/skills}"
dest="$skills_dir/naturali/navigator/SKILL.md"
profiles_dir="${VESSEL_PROFILES_DIR:-$repo_root/../infrastructure/vessels/profiles}"

for f in frontmatter.yaml body.md briefing.md; do
  [ -f "$src/$f" ] || { echo "deploy-navigator: missing $src/$f" >&2; exit 1; }
done

# Resolve the vessel name (see header). Reads YAML with sed — no deps.
resolve_vessel_name() {
  if [ -n "${VESSEL_NAME:-}" ]; then printf '%s' "$VESSEL_NAME"; return; fi
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

vessel_name="$(resolve_vessel_name)"

# 1) Runtime SKILL.md = frontmatter (fenced) + body + briefing,
#    with {{VESSEL_NAME}} substituted.
mkdir -p "$(dirname "$dest")"
tmp="$(mktemp)"
{
  printf -- '---\n'
  cat "$src/frontmatter.yaml"
  printf -- '---\n\n'
  cat "$src/body.md"
  printf '\n'
  cat "$src/briefing.md"
} | sed "s|{{VESSEL_NAME}}|$vessel_name|g" > "$tmp"
mv "$tmp" "$dest"

# 2) Repo doc mirror: prompts/navigator.md = body (no frontmatter, no briefing)
cp "$src/body.md" "$repo_root/prompts/navigator.md"

echo "deploy-navigator: wrote $dest (vessel: $vessel_name)"
echo "deploy-navigator: regenerated $repo_root/prompts/navigator.md"
