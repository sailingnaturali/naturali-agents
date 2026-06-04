#!/usr/bin/env bash
# Assemble the Engineer skill from source fragments and deploy it to the Hermes
# runtime skills tree. Single source of truth lives in skills/engineer/.
#
#   SKILL.md (runtime) = frontmatter.yaml (fenced) + body.md
#   prompts/engineer.md (repo doc) = body.md   (regenerated mirror)
#
# {{VESSEL_NAME}} is substituted with the active vessel's name (see vessel-name.sh).
# The runtime skill is machine-local config (not committed); prompts/engineer.md IS
# committed and keeps the placeholder.
#
# Usage: scripts/deploy-engineer.sh
# Override the destination with HERMES_SKILLS_DIR (default: ~/.hermes/skills).
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/vessel-name.sh
source "$repo_root/scripts/vessel-name.sh"
src="$repo_root/skills/engineer"
skills_dir="${HERMES_SKILLS_DIR:-$HOME/.hermes/skills}"
dest="$skills_dir/naturali/engineer/SKILL.md"

for f in frontmatter.yaml body.md; do
  [ -f "$src/$f" ] || { echo "deploy-engineer: missing $src/$f" >&2; exit 1; }
done

vessel_name="$(resolve_vessel_name "$repo_root")"

mkdir -p "$(dirname "$dest")"
tmp="$(mktemp)"
{
  printf -- '---\n'
  cat "$src/frontmatter.yaml"
  printf -- '---\n\n'
  cat "$src/body.md"
} | sed "s|{{VESSEL_NAME}}|$vessel_name|g" > "$tmp"
mv "$tmp" "$dest"

cp "$src/body.md" "$repo_root/prompts/engineer.md"

echo "deploy-engineer: wrote $dest (vessel: $vessel_name)"
echo "deploy-engineer: regenerated $repo_root/prompts/engineer.md"
