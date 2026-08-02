#!/usr/bin/env bash
# batch-generate.sh — Bulk-create Task-Spec stubs from an intent list.
#
# Usage:
#   bash batch-generate.sh --intent-file <path> --effort S|M [options]
#
# Required flags:
#   --intent-file <path>   File with one "slug: description" per line
#   --effort S|M           Effort class applied to every spec
#
# Optional flags:
#   --agent <name>         Agent hint (default: any)
#   --profile <lvl>        Profile lite|standard|full applied to every spec (default: standard)
#   --source-note <path>   Source provenance applied to every spec
#   --queue                Write to tasks/queue/ instead of tasks/
#   --dry-run              Print what would be created without writing files
#   --skip-validation      Skip the bulk validation pass
#   --validate-opts <opts> Extra flags passed to validate-task-spec.sh
#
# Example:
#   bash batch-generate.sh --intent-file intents.txt --effort S --agent any --queue
#
# Produces: tasks/T-YYYYMMDD-<slug>.md for each intent line
# Updates:  tasks/_state.yaml, tasks/_metrics.jsonl
# Validates: each file with validate-task-spec.sh (unless --skip-validation)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "$SCRIPT_DIR/_lib.sh"
ts_version_flag "$@"

SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Defaults
INTENT_FILE=""
EFFORT=""
AGENT="any"
PROFILE="standard"
SOURCE_NOTE="(none)"
QUEUE=false
DRY_RUN=false
SKIP_VALIDATION=false
VALIDATE_OPTS=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --intent-file)
      INTENT_FILE="${2:-}"
      shift 2
      ;;
    --effort)
      EFFORT="${2:-}"
      shift 2
      ;;
    --agent)
      AGENT="${2:-}"
      shift 2
      ;;
    --profile)
      PROFILE="${2:-standard}"
      shift 2
      ;;
    --source-note)
      SOURCE_NOTE="${2:-}"
      shift 2
      ;;
    --queue)
      QUEUE=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --skip-validation)
      SKIP_VALIDATION=true
      shift
      ;;
    --validate-opts)
      VALIDATE_OPTS="${2:-}"
      shift 2
      ;;
    --help|-h)
      sed -n '2,20p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: batch-generate.sh --intent-file <path> --effort S|M [options]" >&2
      exit 1
      ;;
  esac
done

# Validate required flags
if [[ -z "$INTENT_FILE" ]]; then
  echo "ERROR: --intent-file is required" >&2
  exit 1
fi

if [[ ! -f "$INTENT_FILE" ]]; then
  echo "ERROR: intent file not found: $INTENT_FILE" >&2
  exit 1
fi

if [[ -z "$EFFORT" ]]; then
  echo "ERROR: --effort is required (a leaf tier: XS|S|M|L)" >&2
  exit 1
fi

if ! ts_size_is_leaf "$EFFORT"; then
  if ts_size_is_valid "$EFFORT"; then
    echo "ERROR: '$EFFORT' is a decomposition NODE — nodes are not batch-generated. Author the node individually with a children: block, then batch-generate its leaves. See references/concepts/effort-gate.md" >&2
  else
    echo "ERROR: --effort must be a leaf tier (XS|S|M|L) (got: '$EFFORT')" >&2
  fi
  exit 1
fi

if ! [[ "$AGENT" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "ERROR: agent must contain only letters, digits, dot, underscore, or hyphen" >&2
  exit 1
fi

case "$PROFILE" in
  lite|standard|full) ;;
  *) echo "ERROR: profile must be lite, standard, or full (got: '$PROFILE')" >&2; exit 1 ;;
esac

# Resolve output directory relative to git root
GIT_ROOT=""
if command -v git >/dev/null 2>&1; then
  GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
fi
if [[ -z "$GIT_ROOT" ]]; then
  # Fallback: walk up from intent file
  dir="$(cd "$(dirname "$INTENT_FILE")" && pwd)"
  while [[ "$dir" != "/" ]]; do
    if [[ -d "$dir/.git" ]]; then
      GIT_ROOT="$dir"
      break
    fi
    dir="$(dirname "$dir")"
  done
fi
if [[ -z "$GIT_ROOT" ]]; then
  # Final fallback: use the directory containing the intent file
  # (needed for dry-run or ephemeral workspaces without git)
  GIT_ROOT="$(cd "$(dirname "$INTENT_FILE")" && pwd)"
fi

if [[ "$QUEUE" == true ]]; then
  OUTDIR="$TASKSPEC_BACKLOG_DIR/queue"
else
  OUTDIR="$TASKSPEC_BACKLOG_DIR"
fi

DATE="$(date +%Y%m%d)"
CREATED_AT="$(date -u +%FT%TZ)"

if [[ "$DRY_RUN" == true ]]; then
  echo "[DRY RUN] Would create specs in $OUTDIR from $INTENT_FILE"
  echo ""
fi

# Counters
CREATED_COUNT=0
FAILED=0
VALIDATION_FAILED=0
FILES=()

# Read intent file and generate one spec per line
line_num=0
while IFS= read -r line || [[ -n "$line" ]]; do
  line_num=$((line_num + 1))

  # Skip blank lines and comment lines
  [[ -z "${line// /}" ]] && continue
  [[ "$line" =~ ^[[:space:]]*# ]] && continue

  # Parse "slug: description"
  # Support "slug-one: Fix the first thing" — split on first colon
  slug=""
  description=""
  if [[ "$line" =~ ^([^:]+):[[:space:]]*(.*)$ ]]; then
    slug="${BASH_REMATCH[1]}"
    description="${BASH_REMATCH[2]}"
  else
    echo "WARN: line $line_num does not match 'slug: description' — skipping: $line" >&2
    continue
  fi

  # Trim whitespace
  slug="$(echo "$slug" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  description="$(echo "$description" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

  if [[ -z "$slug" || -z "$description" ]]; then
    echo "WARN: line $line_num has empty slug or description — skipping" >&2
    continue
  fi

  # Validate slug format
  if ! [[ "$slug" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
    echo "ERROR: invalid slug on line $line_num (must be kebab-case): '$slug'" >&2
    FAILED=$((FAILED + 1))
    continue
  fi

  ID="T-${DATE}-${slug}"
  TARGET="$OUTDIR/${ID}.md"

  if [[ -f "$TARGET" ]]; then
    echo "ERROR: $TARGET already exists (line $line_num). Pick a different slug." >&2
    FAILED=$((FAILED + 1))
    continue
  fi

  if [[ "$DRY_RUN" == true ]]; then
    echo "  would create: $TARGET"
    echo "    title: $description"
    echo "    effort: $EFFORT  agent: $AGENT"
    continue
  fi

  mkdir -p "$OUTDIR"

  TEMPLATE="$SKILL_DIR/templates/task-spec.md.tpl"
  if [[ ! -f "$TEMPLATE" ]]; then
    echo "ERROR: template not found at $TEMPLATE" >&2
    exit 1
  fi

  ts_render_template "$TEMPLATE" "$TARGET" \
    ID "$ID" TITLE "$description" STATUS ready PROFILE "$PROFILE" \
    EFFORT "$EFFORT" BUDGET_ITERATIONS 15 AGENT "$AGENT" DEPENDS_ON "[]" \
    TOUCHES_PATHS_YAML "  - {{TODO: path/to/file}}" SOURCE_NOTE "$SOURCE_NOTE" \
    CREATED "$CREATED_AT" TAGS "[]" \
    WHY_ONE_PARAGRAPH "{{TODO: 1-2 sentence why}}" \
    GOAL_ONE_PARAGRAPH "{{TODO: concrete success in one paragraph}}" \
    CONTEXT_LEAN_MAX_100_LINES "{{TODO: lean context, link to existing docs}}" \
    B1_GIVEN "{{TODO: precondition}}" B1_WHEN "{{TODO: action}}" \
    B1_THEN "{{TODO: observable outcome}}" B2_GIVEN "{{TODO: precondition}}" \
    B2_WHEN "{{TODO: action}}" B2_THEN "{{TODO: observable outcome}}" \
    AGENT_PRODUCES "code | docs | config | tests" \
    DO_NOT_TOUCH_LIST "- {{TODO: exact path or (none)}}"

  # Append _metrics.jsonl entry
  METRICS="$TASKSPEC_BACKLOG_DIR/_metrics.jsonl"
  mkdir -p "$TASKSPEC_BACKLOG_DIR"
  ts_append_metric "$METRICS" \
    schema_version 1 ts "$CREATED_AT" task "$ID" event created \
    author "$(whoami)" source "$SOURCE_NOTE" effort "$EFFORT" agent "$AGENT" mode batch

  CREATED_COUNT=$((CREATED_COUNT + 1))
  FILES+=("$TARGET")
  echo "Created $TARGET"
done < "$INTENT_FILE"

if [[ "$DRY_RUN" == true ]]; then
  echo ""
  echo "[DRY RUN] $line_num line(s) read."
  exit 0
fi

# Trigger state rebuild
if [[ -x "$SKILL_DIR/scripts/rebuild-state.sh" ]]; then
  bash "$SKILL_DIR/scripts/rebuild-state.sh" >/dev/null 2>&1 || true
fi

echo ""
echo "=== Batch generate summary ==="
echo "Created: $CREATED_COUNT spec(s)"
echo "Failed:  $FAILED slug(s)"

# Bulk validation
if [[ "$SKIP_VALIDATION" == false && ${#FILES[@]} -gt 0 ]]; then
  echo ""
  echo "=== Bulk validation ==="
  for f in "${FILES[@]}"; do
    # shellcheck disable=SC2086
    if bash "$SKILL_DIR/scripts/validate-task-spec.sh" $VALIDATE_OPTS "$f" >/dev/null 2>&1; then
      echo "OK:   $(basename "$f")"
    else
      echo "FAIL: $(basename "$f")"
      VALIDATION_FAILED=$((VALIDATION_FAILED + 1))
    fi
  done
fi

echo ""
echo "Next steps:"
echo "  1. Fill in the {{TODO}} stubs in each generated file"
echo "  2. Re-run validation after editing:"
echo "     bash $SKILL_DIR/scripts/validate-task-spec.sh $OUTDIR/T-*.md"
echo "  3. Commit:"
echo "     git add $OUTDIR/"

if [[ "$FAILED" -gt 0 || "$VALIDATION_FAILED" -gt 0 ]]; then
  exit 1
fi

exit 0
