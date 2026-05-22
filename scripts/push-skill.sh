#!/usr/bin/env bash
# Copy a skill or plugin from your vault to the repo working copy, ready to commit.
#
# Usage:
#   ./scripts/push-skill.sh <name>    # stage a plugin or skill for publishing

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VAULT="${HOME}/.snowflake/cortex/vault"

[ -z "${1:-}" ] && echo "Usage: $0 <skill-or-plugin-name>" && exit 1

name=$1

if [ -d "$VAULT/plugins/$name" ]; then
  type=plugins
elif [ -d "$VAULT/skills/$name" ]; then
  type=skills
else
  echo "ERROR: '$name' not found in vault plugins/ or skills/"
  exit 1
fi

src="$VAULT/$type/$name"
dst="$REPO_DIR/$type/$name"

rsync -a --delete --exclude='.my_skill' "$src/" "$dst/"
echo "STAGED $type/$name"
echo ""
echo "Review changes:"
echo "  git -C $REPO_DIR diff --stat"
echo ""
echo "Then commit and push:"
echo "  git -C $REPO_DIR add $type/$name"
echo "  git -C $REPO_DIR commit -m 'skill: publish $name'"
echo "  git -C $REPO_DIR push"
echo ""

# Remind about registry if this looks like a new skill
if ! grep -q "$name" "$REPO_DIR/skill-loader/SKILL.md" 2>/dev/null; then
  echo "NOTE: '$name' not found in skill-loader/SKILL.md — add a registry entry before pushing."
fi
