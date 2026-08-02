#!/usr/bin/env bash
# transition-status.sh — Atomically transition a task's status.
#
# Usage:
#   bash transition-status.sh <task-id> <new-status> [reason]
#
# Statuses: ready | in-progress | blocked | done | parked

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "$SCRIPT_DIR/_lib.sh"
ts_version_flag "$@"

TASK_ID="${1:?Usage: transition-status.sh <task-id> <new-status> [reason]}"
NEW_STATUS="${2:?new-status required}"
REASON="${3:-}"

case "$NEW_STATUS" in
  ready|in-progress|blocked|done|parked) ;;
  *) echo "ERROR: invalid status '$NEW_STATUS'" >&2; exit 1 ;;
esac

TASK_FILE=""
for candidate in \
  "$TASKSPEC_BACKLOG_DIR/${TASK_ID}.md" \
  "$TASKSPEC_BACKLOG_DIR/done/${TASK_ID}.md" \
  "$TASKSPEC_BACKLOG_DIR/parked/${TASK_ID}.md"; do
  if [[ -f "$candidate" ]]; then
    TASK_FILE="$candidate"
    break
  fi
done

if [[ -z "$TASK_FILE" ]]; then
  echo "ERROR: task ${TASK_ID} not found" >&2
  exit 1
fi

mkdir -p "$TASKSPEC_BACKLOG_DIR"
LOCK_FILE="$TASKSPEC_BACKLOG_DIR/.state.lock"
# Portable advisory lock (ts_lock_* uses an atomic mkdir — works on macOS, which
# ships no `flock`). Released on every exit path via the trap below.
if ! ts_lock_acquire "$LOCK_FILE"; then
  echo "ERROR: another process holds the state lock" >&2
  exit 1
fi
trap 'ts_lock_release "$LOCK_FILE"' EXIT

CURRENT=$(grep '^status:' "$TASK_FILE" | head -1 | awk '{print $2}')

if [[ "$CURRENT" == "$NEW_STATUS" ]]; then
  echo "NOOP: $TASK_ID already at status '$NEW_STATUS'"
  exit 0
fi

if [[ "$NEW_STATUS" == "done" ]]; then
  ACCEPTED=$(grep -m1 '^accepted:' "$TASK_FILE" 2>/dev/null | awk -F: '{print $2}' | xargs || true)
  ACCEPTED_BY=$(grep -m1 '^accepted_by:' "$TASK_FILE" 2>/dev/null | sed -E 's/^accepted_by:[[:space:]]*//' || true)
  ACCEPTED_AT=$(grep -m1 '^accepted_at:' "$TASK_FILE" 2>/dev/null | sed -E 's/^accepted_at:[[:space:]]*//' || true)
  if [[ "$ACCEPTED" != "true" || -z "$ACCEPTED_BY" || "$ACCEPTED_BY" == "(none)" \
    || -z "$ACCEPTED_AT" || "$ACCEPTED_AT" == "(none)" ]]; then
    echo "ERROR: $TASK_ID cannot enter done until cvg tasks accept --stamp records accepted:true, accepted_by, and accepted_at" >&2
    exit 1
  fi
  WORKSPACE_ROOT="$(ts_workspace_root "$TASK_FILE")"
  RECEIPT="$WORKSPACE_ROOT/cvg/receipts/${TASK_ID}.json"
  if [[ ! -f "$RECEIPT" ]]; then
    echo "ERROR: $TASK_ID cannot enter done without a passing execution receipt at $RECEIPT" >&2
    exit 1
  fi
  if ! python3 - "$RECEIPT" "$TASK_ID" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    receipt = json.load(handle)
assert receipt.get("task_id") == sys.argv[2]
assert receipt.get("result") == "pass"
PY
  then
    echo "ERROR: $TASK_ID receipt is malformed, belongs to another task, or is not result:pass" >&2
    exit 1
  fi
fi

TMP="${TASK_FILE}.tmp.$$"
ts_prepare_tmp "$TMP"
awk -v new="$NEW_STATUS" '
  /^status:/ && !done { print "status: " new; done=1; next }
  { print }
' "$TASK_FILE" > "$TMP"
mv "$TMP" "$TASK_FILE"

TARGET_LOC="$TASK_FILE"
case "$NEW_STATUS" in
  done)
    mkdir -p "$TASKSPEC_BACKLOG_DIR/done"
    TARGET_LOC="$TASKSPEC_BACKLOG_DIR/done/${TASK_ID}.md"
    [[ "$TASK_FILE" != "$TARGET_LOC" ]] && mv "$TASK_FILE" "$TARGET_LOC"
    ;;
  parked)
    mkdir -p "$TASKSPEC_BACKLOG_DIR/parked"
    TARGET_LOC="$TASKSPEC_BACKLOG_DIR/parked/${TASK_ID}.md"
    [[ "$TASK_FILE" != "$TARGET_LOC" ]] && mv "$TASK_FILE" "$TARGET_LOC"
    ;;
  ready|in-progress|blocked)
    if [[ "$TASK_FILE" == "$TASKSPEC_BACKLOG_DIR/done"/* || "$TASK_FILE" == "$TASKSPEC_BACKLOG_DIR/parked"/* ]]; then
      TARGET_LOC="$TASKSPEC_BACKLOG_DIR/${TASK_ID}.md"
      mv "$TASK_FILE" "$TARGET_LOC"
    fi
    ;;
esac

TS="$(date -u +%FT%TZ)"
METRIC_ARGS=(schema_version 1 ts "$TS" task "$TASK_ID" event status_change from "$CURRENT" to "$NEW_STATUS")
if [[ -n "$REASON" ]]; then
  METRIC_ARGS+=(reason "$REASON")
fi
ts_append_metric "$TASKSPEC_BACKLOG_DIR/_metrics.jsonl" "${METRIC_ARGS[@]}"

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -x "$SKILL_DIR/scripts/rebuild-state.sh" ]]; then
  bash "$SKILL_DIR/scripts/rebuild-state.sh" >/dev/null 2>&1 || true
fi

echo ">>> $TASK_ID: $CURRENT -> $NEW_STATUS"
echo "    file: $TARGET_LOC"
if [[ -n "$REASON" ]]; then
  echo "    reason: $REASON"
fi
