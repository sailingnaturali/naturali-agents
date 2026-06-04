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
# shellcheck source=scripts/vessel-name.sh
source "$repo_root/scripts/vessel-name.sh"
src="$repo_root/skills/navigator"
skills_dir="${HERMES_SKILLS_DIR:-$HOME/.hermes/skills}"
dest="$skills_dir/naturali/navigator/SKILL.md"

for f in frontmatter.yaml body.md briefing.md; do
  [ -f "$src/$f" ] || { echo "deploy-navigator: missing $src/$f" >&2; exit 1; }
done

vessel_name="$(resolve_vessel_name "$repo_root")"

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
