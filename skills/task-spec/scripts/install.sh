#!/usr/bin/env bash
# install.sh — Portable installer for the task-spec skill.
#
# Defaults to project-local install at $TARGET/.claude/skills/task-spec/.
# Use --global to install at ~/.claude/skills/task-spec/ instead.
# Use --namespace=<name> to override the agent filename to avoid collision with
# an existing `task-architect` agent in the target repo.
#
# Usage:
#   bash install.sh                              # install in current repo (PWD)
#   bash install.sh --target /path/to/repo       # install in a specific repo
#   bash install.sh --global                     # install at ~/.claude/skills/
#   bash install.sh --namespace=my-task          # use my-task-architect.md
#   bash install.sh --version                    # print version and exit
#
# Exit codes:
#   0   success (or already installed — idempotent)
#   1   usage error
#   2   target not writable / IO error

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "$SCRIPT_DIR/_lib.sh"
ts_version_flag "$@"

SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILL_NAME="task-spec"
TARGET=""
GLOBAL=false
NAMESPACE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target=*)   TARGET="${1#*=}"; shift ;;
    --target)     TARGET="${2:-}"; shift 2 ;;
    --global)     GLOBAL=true; shift ;;
    --namespace=*) NAMESPACE="${1#*=}"; shift ;;
    --namespace)  NAMESPACE="${2:-}"; shift 2 ;;
    --help|-h)
      sed -n '2,18p' "$0"; exit 0 ;;
    *) ts_die "Unknown option: $1" ;;
  esac
done

# Resolve install root
if [[ "$GLOBAL" == "true" ]]; then
  INSTALL_ROOT="$HOME/.claude/skills/$SKILL_NAME"
else
  TARGET="${TARGET:-$PWD}"
  if [[ ! -d "$TARGET" ]]; then
    ts_die "Target directory does not exist: $TARGET"
  fi
  INSTALL_ROOT="$TARGET/.claude/skills/$SKILL_NAME"
fi

echo "Installing task-spec v$TASKSPEC_VERSION → $INSTALL_ROOT"

mkdir -p "$INSTALL_ROOT" || ts_die "cannot create $INSTALL_ROOT"

# Copy everything EXCEPT .git-like artifacts and the existing INSTALL_ROOT
# (in case skill is installing to a subdir of itself).
find "$SKILL_DIR" -mindepth 1 -maxdepth 1 \
  -not -name '.git' -not -name '.DS_Store' \
  -not -name 'CHANGELOG.md.bak' \
  | while read -r item; do
    # Don't recurse into the install target itself
    if [[ "$item" == "$INSTALL_ROOT" || "$item" == "$INSTALL_ROOT"/* ]]; then continue; fi
    name="$(basename "$item")"
    if [[ -d "$item" ]]; then
      cp -R "$item" "$INSTALL_ROOT/$name"
    else
      cp "$item" "$INSTALL_ROOT/$name"
    fi
  done

# Optionally namespace the bundled agent to avoid collision
if [[ -n "$NAMESPACE" && -d "$INSTALL_ROOT/agents" ]]; then
  for f in "$INSTALL_ROOT"/agents/*.md; do
    [[ -e "$f" ]] || continue
    base="$(basename "$f")"
    new_base="${NAMESPACE}-${base}"
    mv "$f" "$INSTALL_ROOT/agents/$new_base"
    echo "  namespaced: agents/$base → agents/$new_base"
  done
fi

# Also install the agent to ~/.claude/agents/ for Claude Code discovery
# (only when --global; for project-local install the agent lives only at
# project_root/.claude/skills/task-spec/agents/)
if [[ "$GLOBAL" == "true" && -d "$INSTALL_ROOT/agents" ]]; then
  AGENTS_DST="$HOME/.claude/agents"
  mkdir -p "$AGENTS_DST"
  for f in "$INSTALL_ROOT"/agents/*.md; do
    [[ -e "$f" ]] || continue
    name="$(basename "$f")"
    if [[ -f "$AGENTS_DST/$name" ]]; then
      echo "  SKIP: $AGENTS_DST/$name already exists"
    else
      cp "$f" "$AGENTS_DST/$name"
      echo "  agent: $AGENTS_DST/$name"
    fi
  done
fi

echo ""
echo "Done. task-spec v$TASKSPEC_VERSION installed at:"
echo "  $INSTALL_ROOT"
echo ""
echo "Next: bash $INSTALL_ROOT/scripts/generate-task-spec.sh <slug> <effort>"
echo ""
echo "Configure backlog directory (optional):"
echo "  export TASKSPEC_BACKLOG_DIR=path/to/backlog   # default: tasks"
