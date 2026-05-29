#!/usr/bin/env bash
# Assemble the Navigator skill from source fragments and deploy it to the
# Hermes runtime skills tree. Single source of truth lives in
# skills/navigator/ — this is the only thing that should write SKILL.md.
#
#   SKILL.md (runtime) = frontmatter.yaml (fenced) + body.md + briefing.md
#   prompts/navigator.md (repo doc) = body.md   (regenerated mirror)
#
# The runtime skill is machine-local config (not committed). prompts/navigator.md
# IS committed, so the documented prompt can never drift from what runs.
#
# Usage: scripts/deploy-navigator.sh
# Override the destination with HERMES_SKILLS_DIR (default: ~/.hermes/skills).
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
src="$repo_root/skills/navigator"
skills_dir="${HERMES_SKILLS_DIR:-$HOME/.hermes/skills}"
dest="$skills_dir/naturali/navigator/SKILL.md"

for f in frontmatter.yaml body.md briefing.md; do
  [ -f "$src/$f" ] || { echo "deploy-navigator: missing $src/$f" >&2; exit 1; }
done

# 1) Runtime SKILL.md = frontmatter (fenced) + body + briefing
mkdir -p "$(dirname "$dest")"
tmp="$(mktemp)"
{
  printf -- '---\n'
  cat "$src/frontmatter.yaml"
  printf -- '---\n\n'
  cat "$src/body.md"
  printf '\n'
  cat "$src/briefing.md"
} > "$tmp"
mv "$tmp" "$dest"

# 2) Repo doc mirror: prompts/navigator.md = body (no frontmatter, no briefing)
cp "$src/body.md" "$repo_root/prompts/navigator.md"

echo "deploy-navigator: wrote $dest"
echo "deploy-navigator: regenerated $repo_root/prompts/navigator.md"
