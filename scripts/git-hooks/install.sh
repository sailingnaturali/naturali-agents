#!/usr/bin/env bash
# Install this repo's git hooks. Run once per clone.
set -euo pipefail
repo_root="$(git rev-parse --show-toplevel)"
ln -sf ../../scripts/git-hooks/pre-commit "$repo_root/.git/hooks/pre-commit"
echo "installed: .git/hooks/pre-commit -> scripts/git-hooks/pre-commit"
