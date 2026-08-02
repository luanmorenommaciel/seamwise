#!/usr/bin/env bash
# generate-task-spec.sh — Create a new Task-Spec file (current format) from the template.
#
# Usage:
#   bash generate-task-spec.sh [--status=ready|blocked] [--queue] <slug> <effort> [agent] [source_note]
#
# Example:
#   bash generate-task-spec.sh verify-langfuse-otel S any notes/2026-05-04-observability.md
#   bash generate-task-spec.sh --status=blocked --queue fix-login-redirect S
#
# Produces: tasks/T-YYYYMMDD-<slug>.md (filled from template; stubs marked {{TODO}})
# Updates: tasks/_state.yaml
# Logs: tasks/_metrics.jsonl

set -euo pipefail

# Source shared lib (TASKSPEC_VERSION, ts_version_flag, ts_die)
_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
# shellcheck source=./_lib.sh
source "$_LIB"

# Handle --version uniformly across all task-spec scripts
ts_version_flag "$@"

STATUS="ready"
QUEUE=false
PROFILE="standard"

# Parse flags
ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --status=*)
      STATUS="${1#*=}"
      shift
      ;;
    --status)
      STATUS="${2:-ready}"
      shift 2
      ;;
    --profile=*)
      PROFILE="${1#*=}"
      shift
      ;;
    --profile)
      PROFILE="${2:-standard}"
      shift 2
      ;;
    --queue)
      QUEUE=true
      shift
      ;;
    --help|-h)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    --)
      shift
      ARGS+=("$@")
      break
      ;;
    -*)
      echo "Unknown option: $1" >&2
      echo "Usage: generate-task-spec.sh [--status=ready|blocked] [--queue] <slug> <effort> [agent] [source_note]" >&2
      exit 1
      ;;
    *)
      ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ ${#ARGS[@]} -lt 2 ]]; then
  echo "Usage: generate-task-spec.sh [--status=ready|blocked] [--queue] <slug> <effort> [agent] [source_note]" >&2
  exit 1
fi

SLUG="${ARGS[0]}"
EFFORT="${ARGS[1]}"
AGENT="${ARGS[2]:-any}"
SOURCE_NOTE="${ARGS[3]:-(none)}"

if ! [[ "$AGENT" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "ERROR: agent must contain only letters, digits, dot, underscore, or hyphen" >&2
  exit 1
fi

if ! ts_size_is_valid "$EFFORT"; then
  echo "ERROR: effort must be one of $TS_SIZES (got: '$EFFORT'). See references/concepts/effort-gate.md" >&2
  exit 1
fi
if ! ts_size_is_leaf "$EFFORT"; then
  echo "NOTE: '$EFFORT' is a decomposition NODE, not a runnable leaf. This stub will need a" >&2
  echo "      children: block ($(ts_size_min_children "$EFFORT")+ child task-spec ids) before it can be delegated —" >&2
  echo "      the worker dispatches the children (leaves), never the node. See references/concepts/effort-gate.md" >&2
fi

case "$PROFILE" in
  lite|standard|full) ;;
  *)
    echo "ERROR: profile must be lite, standard, or full (got: '$PROFILE')" >&2
    exit 1
    ;;
esac

if ! [[ "$SLUG" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
  echo "ERROR: slug must be lowercase kebab-case (e.g., 'verify-langfuse-otel')" >&2
  exit 1
fi

DATE="$(date +%Y%m%d)"
CREATED="$(date -u +%FT%TZ)"
ID="T-${DATE}-${SLUG}"

if [[ "$QUEUE" == true ]]; then
  OUTDIR="$TASKSPEC_BACKLOG_DIR/queue"
else
  OUTDIR="$TASKSPEC_BACKLOG_DIR"
fi

TARGET="$OUTDIR/${ID}.md"

if [[ -f "$TARGET" ]]; then
  echo "ERROR: $TARGET already exists. Pick a different slug." >&2
  exit 1
fi

mkdir -p "$OUTDIR"

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$SKILL_DIR/templates/task-spec.md.tpl"

if [[ ! -f "$TEMPLATE" ]]; then
  echo "ERROR: template not found at $TEMPLATE" >&2
  exit 1
fi

ts_render_template "$TEMPLATE" "$TARGET" \
  ID "$ID" TITLE "{{TODO: one-line title in imperative voice}}" \
  STATUS "$STATUS" PROFILE "$PROFILE" EFFORT "$EFFORT" \
  BUDGET_ITERATIONS 15 AGENT "$AGENT" DEPENDS_ON "[]" \
  TOUCHES_PATHS_YAML "  - {{TODO: path/to/file}}" SOURCE_NOTE "$SOURCE_NOTE" \
  CREATED "$CREATED" TAGS "[]" \
  WHY_ONE_PARAGRAPH "{{TODO: 1-2 sentence why}}" \
  GOAL_ONE_PARAGRAPH "{{TODO: concrete success in one paragraph}}" \
  CONTEXT_LEAN_MAX_100_LINES "{{TODO: lean context, link to existing docs}}" \
  B1_GIVEN "{{TODO: precondition}}" B1_WHEN "{{TODO: action}}" \
  B1_THEN "{{TODO: observable outcome}}" B2_GIVEN "{{TODO: precondition}}" \
  B2_WHEN "{{TODO: action}}" B2_THEN "{{TODO: observable outcome}}" \
  AGENT_PRODUCES "code | docs | config | tests" \
  DO_NOT_TOUCH_LIST "- {{TODO: exact path or (none)}}"

# Append _metrics.jsonl entry
mkdir -p "$TASKSPEC_BACKLOG_DIR"
METRICS="$TASKSPEC_BACKLOG_DIR/_metrics.jsonl"
ts_append_metric "$METRICS" \
  schema_version 1 ts "$CREATED" task "$ID" event created \
  author "$(whoami)" source "$SOURCE_NOTE" effort "$EFFORT" agent "$AGENT"

# Trigger state rebuild
if [[ -x "$SKILL_DIR/scripts/rebuild-state.sh" ]]; then
  bash "$SKILL_DIR/scripts/rebuild-state.sh" >/dev/null 2>&1 || true
fi

echo "Spec written: $TARGET"
echo "  status: $STATUS  outdir: $OUTDIR  task_spec_version: $TASKSPEC_VERSION"
echo ""
echo "Next steps:"
echo ""
echo "  1. Fill in the {{TODO}} stubs:"
echo "     - title"
echo "     - touches_paths"
echo "     - why / goal / context"
echo "     - eval_1, eval_2, eval_3 (runnable bash — avoid the inverted-grep-c"
echo "       footgun; use '! grep -q PATTERN file' instead of '\$(grep -c X file"
echo "       || echo 0); [ \"\$count\" -eq 0 ]')"
echo "     - anti-patterns + do-not-touch"
echo ""
echo "  2. VALIDATE (pre-gate structural linter — does NOT stamp signed_off):"
echo "     bash $SKILL_DIR/scripts/validate-task-spec.sh $TARGET"
echo ""
echo "Next: bash $SKILL_DIR/scripts/safe-to-delegate.sh --stamp $TARGET"
echo ""
echo "     The gate is THE only path to signed_off:true. Hand-stamping the"
echo "     signed_off field is rejected by the structural sign-off envelope check."
echo "     See: references/concepts/signed-off.md"
echo ""
echo "  3. DISPATCH (after the gate stamps signed_off:true):"
echo "     See runbooks/dispatching-a-task-spec.md for the handoff protocol"
echo "     per execution_backend (kimi, claude, codex, taskship, ...)."
