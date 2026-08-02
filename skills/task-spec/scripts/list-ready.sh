#!/usr/bin/env bash
# list-ready.sh — Show all tasks ready for pickup.
#
# Usage:
#   bash list-ready.sh                # the FRONTIER — ready AND unblocked
#   bash list-ready.sh --all          # every status:ready spec, blocked or not
#   bash list-ready.sh --effort=S     # only S-effort
#   bash list-ready.sh --agent=any    # only agent-agnostic tasks
#
# "Ready" means dispatchable. A spec whose depends_on is unmet is NOT
# dispatchable, however green its own status field looks — handing one to a
# worker starts work whose inputs do not exist yet. This is the selection
# surface a Manager reads, so it fails closed: a dangling depends_on (a target
# that is not in the backlog at all) counts as UNMET.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "$SCRIPT_DIR/_lib.sh"
ts_version_flag "$@"

FILTER_EFFORT=""
FILTER_AGENT=""
SHOW_ALL=0

for arg in "$@"; do
  case "$arg" in
    --effort=*) FILTER_EFFORT="${arg#--effort=}" ;;
    --agent=*) FILTER_AGENT="${arg#--agent=}" ;;
    --all) SHOW_ALL=1 ;;
  esac
done

# Every depends_on id in a spec. Handles both the inline form
# (`depends_on: [T-a, T-b]`) and the block list form.
_deps_of() {
  awk '/^depends_on:/{f=1; print; next} f && /^[a-z_]+:/{exit} f' "$1" 2>/dev/null \
    | grep -oE 'T-[0-9]{8}-[A-Za-z0-9_-]+' || true
}

# A dependency counts as met only when its spec exists AND has reached a
# terminal state. Anything else — in progress, parked, or missing entirely —
# leaves the dependent task blocked.
_dep_met() {
  _dm_dep="$1"
  for _dm_f in "$TASKSPEC_BACKLOG_DIR"/T-*.md "$TASKSPEC_BACKLOG_DIR"/done/T-*.md; do
    [[ -f "$_dm_f" ]] || continue
    [[ "$(grep -m1 '^id:' "$_dm_f" | awk '{print $2}')" == "$_dm_dep" ]] || continue
    case "$(grep -m1 '^status:' "$_dm_f" | awk '{print $2}')" in
      done|accepted) return 0 ;;
      *)             return 1 ;;
    esac
  done
  return 1
}

if [[ ! -d "$TASKSPEC_BACKLOG_DIR" ]]; then
  echo "(no $TASKSPEC_BACKLOG_DIR/ directory in $(pwd))"
  exit 0
fi

printf "%-32s %-7s %-12s %s\n" "ID" "EFFORT" "AGENT" "TITLE"
printf "%-32s %-7s %-12s %s\n" "$(printf '=%.0s' {1..32})" "======" "============" "$(printf '=%.0s' {1..50})"

for FILE in "$TASKSPEC_BACKLOG_DIR"/T-*.md; do
  [[ -f "$FILE" ]] || continue

  STATUS=$(grep '^status:' "$FILE" | head -1 | awk '{print $2}')
  [[ "$STATUS" == "ready" ]] || continue

  if [[ "$SHOW_ALL" -eq 0 ]]; then
    BLOCKED=0
    while IFS= read -r DEP; do
      [[ -n "$DEP" ]] || continue
      _dep_met "$DEP" || { BLOCKED=1; break; }
    done <<< "$(_deps_of "$FILE")"
    [[ "$BLOCKED" -eq 0 ]] || { SKIPPED=$((${SKIPPED:-0} + 1)); continue; }
  fi

  EFFORT=$(grep '^effort:' "$FILE" | head -1 | awk '{print $2}')
  AGENT=$(grep '^agent:' "$FILE" | head -1 | awk '{print $2}')
  ID=$(grep '^id:' "$FILE" | head -1 | awk '{print $2}')
  TITLE=$(grep '^title:' "$FILE" | head -1 | sed 's/^title: *//')

  [[ -n "$FILTER_EFFORT" && "$EFFORT" != "$FILTER_EFFORT" ]] && continue
  [[ -n "$FILTER_AGENT" && "$AGENT" != "$FILTER_AGENT" ]] && continue

  printf "%-32s %-7s %-12s %s\n" "$ID" "$EFFORT" "$AGENT" "${TITLE:0:60}"
done

if [[ "$SHOW_ALL" -eq 0 && "${SKIPPED:-0}" -gt 0 ]]; then
  printf '\n(%d ready spec(s) hidden — blocked by an unmet depends_on; --all shows them)\n' "${SKIPPED:-0}"
fi
