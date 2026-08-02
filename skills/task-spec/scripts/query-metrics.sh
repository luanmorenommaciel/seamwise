#!/usr/bin/env bash
# query-metrics.sh — Query tasks/_metrics.jsonl with filters.
#
# Usage:
#   bash query-metrics.sh [--since YYYY-MM-DD] [--author <name>] [--status <status>]
#
# Filters:
#   --since <date>     Only entries on or after this ISO date (compares against ts)
#   --author <name>    Only entries by this author
#   --status <status>  Only tasks whose current frontmatter/status matches
#
# Dependencies:
#   jq recommended for robust JSON parsing; falls back to grep (coarse) if absent.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "$SCRIPT_DIR/_lib.sh"
ts_version_flag "$@"
ts_require_bash4 "$@"
METRICS="$TASKSPEC_BACKLOG_DIR/_metrics.jsonl"
STATE="$TASKSPEC_BACKLOG_DIR/_state.yaml"

SINCE=""
AUTHOR=""
STATUS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --since)
      SINCE="${2:-}"
      shift 2
      ;;
    --author)
      AUTHOR="${2:-}"
      shift 2
      ;;
    --status)
      STATUS="${2:-}"
      shift 2
      ;;
    --help|-h)
      sed -n '2,13p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: query-metrics.sh [--since YYYY-MM-DD] [--author <name>] [--status <status>]" >&2
      exit 1
      ;;
  esac
done

if [[ ! -f "$METRICS" ]]; then
  echo "No metrics file found at $METRICS" >&2
  exit 1
fi

# Prefer jq; warn if absent
if command -v jq >/dev/null 2>&1; then
  USE_JQ=true
else
  USE_JQ=false
  echo "WARN: jq not installed; using grep fallback (coarse JSON filtering)." >&2
  echo "      Install jq for precise queries: https://jqlang.github.io/jq/" >&2
  echo "" >&2
fi

# Build a lookup of task_id -> current status
declare -A STATUS_MAP
if [[ -n "$STATUS" ]]; then
  if [[ -f "$STATE" ]]; then
    while IFS= read -r line; do
      if [[ "$line" =~ ^[[:space:]]*-[[:space:]]*id:[[:space:]]*(.*)$ ]]; then
        CURRENT_ID="${BASH_REMATCH[1]}"
      elif [[ "$line" =~ ^[[:space:]]*status:[[:space:]]*(.*)$ ]]; then
        if [[ -n "${CURRENT_ID:-}" ]]; then
          STATUS_MAP["$CURRENT_ID"]="${BASH_REMATCH[1]}"
          CURRENT_ID=""
        fi
      fi
    done < "$STATE"
  fi

  # Fallback: scan task files for any IDs missing from state
  while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    bn=$(basename "$f" .md)
    if [[ -z "${STATUS_MAP[$bn]:-}" ]]; then
      st=$(grep '^status:' "$f" | head -1 | awk '{print $2}' || true)
      [[ -n "$st" ]] && STATUS_MAP["$bn"]="$st"
    fi
  done < <(find "$TASKSPEC_BACKLOG_DIR" -type f -name 'T-*.md' | sort)
fi

MATCH_COUNT=0

while IFS= read -r line; do
  [[ -n "$line" ]] || continue

  match=true

  # --since filter
  if [[ -n "$SINCE" ]]; then
    if [[ "$USE_JQ" == true ]]; then
      ts=$(echo "$line" | jq -r '.ts // ""')
    else
      ts=$(echo "$line" | grep -o '"ts":"[^"]*"' | sed 's/"ts":"//;s/"$//' || true)
    fi
    # Compare lexicographically (ISO 8601 works with string compare)
    if [[ "${ts:-}" < "${SINCE}T00:00:00Z" ]]; then
      match=false
    fi
  fi

  # --author filter
  if [[ -n "$AUTHOR" && "$match" == true ]]; then
    if [[ "$USE_JQ" == true ]]; then
      au=$(echo "$line" | jq -r '.author // ""')
    else
      au=$(echo "$line" | grep -o '"author":"[^"]*"' | sed 's/"author":"//;s/"$//' || true)
    fi
    if [[ "${au:-}" != "$AUTHOR" ]]; then
      match=false
    fi
  fi

  # --status filter
  if [[ -n "$STATUS" && "$match" == true ]]; then
    if [[ "$USE_JQ" == true ]]; then
      task_id=$(echo "$line" | jq -r '.task // ""')
    else
      task_id=$(echo "$line" | grep -o '"task":"[^"]*"' | sed 's/"task":"//;s/"$//' || true)
    fi
    current_status="${STATUS_MAP[${task_id:-}]:-}"
    if [[ "$current_status" != "$STATUS" ]]; then
      match=false
    fi
  fi

  if [[ "$match" == true ]]; then
    echo "$line"
    MATCH_COUNT=$((MATCH_COUNT + 1))
  fi
done < "$METRICS"

echo "" >&2
echo "Matched $MATCH_COUNT record(s)" >&2
