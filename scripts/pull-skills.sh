#!/usr/bin/env bash
# Pull skills/plugins from the shared repo into your local vault.
#
# Usage:
#   ./scripts/pull-skills.sh                   # show what's available / changed
#   ./scripts/pull-skills.sh <name>            # pull one plugin or skill by name
#   ./scripts/pull-skills.sh --all             # pull everything (skips .my_skill dirs)
#   ./scripts/pull-skills.sh --dry-run         # show what --all would change

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VAULT="${HOME}/.snowflake/cortex/vault"

pull_item() {
  local type=$1   # plugins or skills
  local name=$2
  local src="$REPO_DIR/$type/$name"
  local dst="$VAULT/$type/$name"

  if [ -f "$dst/.my_skill" ]; then
    echo "SKIP  $type/$name  (personal — .my_skill marker present)"
    return 0
  fi

  mkdir -p "$dst"
  rsync -a --delete "$src/" "$dst/"
  echo "PULLED $type/$name"
}

case "${1:-}" in
  --all)
    echo "Pulling all plugins..."
    for dir in "$REPO_DIR/plugins"/*/; do
      [ -d "$dir" ] && pull_item plugins "$(basename "$dir")"
    done
    echo "Pulling all skills..."
    for dir in "$REPO_DIR/skills"/*/; do
      [ -d "$dir" ] && pull_item skills "$(basename "$dir")"
    done
    ;;

  --dry-run)
    echo "Dry run — changes that would be applied:"
    for type in plugins skills; do
      for dir in "$REPO_DIR/$type"/*/; do
        [ -d "$dir" ] || continue
        name=$(basename "$dir")
        dst="$VAULT/$type/$name"
        if [ -f "$dst/.my_skill" ]; then
          echo "  SKIP  $type/$name  (personal)"
        elif [ ! -d "$dst" ]; then
          echo "  NEW   $type/$name"
        else
          diff_out=$(rsync -ain --delete "$dir" "$dst/" | grep -v '^\.' || true)
          [ -n "$diff_out" ] && echo "  UPDATE $type/$name" || echo "  SAME   $type/$name"
        fi
      done
    done
    ;;

  "")
    echo "cortex-config skill vault"
    echo ""
    echo "Plugins ($(ls "$REPO_DIR/plugins" | wc -l | tr -d ' ')):"
    ls "$REPO_DIR/plugins"
    echo ""
    echo "Skills ($(ls "$REPO_DIR/skills" | wc -l | tr -d ' ')):"
    ls "$REPO_DIR/skills"
    echo ""
    echo "Usage:"
    echo "  $0 <name>      pull one skill or plugin"
    echo "  $0 --all       pull everything"
    echo "  $0 --dry-run   preview changes"
    ;;

  *)
    name=$1
    if [ -d "$REPO_DIR/plugins/$name" ]; then
      pull_item plugins "$name"
    elif [ -d "$REPO_DIR/skills/$name" ]; then
      pull_item skills "$name"
    else
      echo "ERROR: '$name' not found in plugins/ or skills/"
      echo ""
      echo "Available plugins: $(ls "$REPO_DIR/plugins" | tr '\n' ' ')"
      echo "Available skills:  $(ls "$REPO_DIR/skills" | tr '\n' ' ')"
      exit 1
    fi
    ;;
esac
