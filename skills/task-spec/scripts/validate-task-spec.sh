#!/usr/bin/env bash
# validate-task-spec.sh — Lint a Task-Spec file against the current (v3) format; legacy v0/v1/v2 accepted with warnings.
#
# Position: pre-gate STRUCTURAL linter. Does NOT execute evals. Does NOT stamp signed_off.
# The autonomy contract is produced by safe-to-delegate.sh --stamp (the gate).
# See references/concepts/signed-off.md for the validate-vs-gate contract.
#
# Usage:
#   bash validate-task-spec.sh [options] <path/to/T-*.md>
#
# Options:
#   --strict-depends         Hard-fail on depends_on referencing parked/done tasks
#   --skip-id-filename       Skip id vs filename basename check
#   --skip-depends-on        Skip depends_on existence check
#   --skip-touches-paths     Skip touches_paths existence check
#   --skip-exit-coverage     Skip Exit Check coverage check
#   --shellcheck-evals       Run shellcheck on eval_N() bodies (opt-in, requires shellcheck)
#   --dry-run-eval           Source evals in a disposable subshell and run Exit Check (opt-in)
#   --no-state               Validate read-only; do not refresh tasks/_state.yaml
#
# Exit codes:
#   0 — valid Task-Spec (current v3, or v2/v1) OR accepted legacy v0/v1/v2 with warnings
#   1 — missing required fields or zones
#   2 — invalid field values
#   3 — leftover placeholders or stubs

set -euo pipefail

# Source shared lib (TASKSPEC_VERSION, ts_version_flag, ts_die)
_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
# shellcheck source=./_lib.sh
source "$_LIB"

# Handle --version uniformly across all task-spec scripts
ts_version_flag "$@"

# --emit-schema <name> — print one of the published JSON Schemas to stdout and exit 0.
# Makes this script the single source of truth for downstream consumers.
# Supported names: frontmatter, agent-contract.
if [[ "${1:-}" == "--emit-schema" ]]; then
  case "${2:-}" in
    frontmatter)
      cat "$TASKSPEC_SKILL_DIR/references/schemas/task-spec-frontmatter.schema.json"
      exit 0
      ;;
    agent-contract)
      cat "$TASKSPEC_SKILL_DIR/references/schemas/agent-contract.schema.json"
      exit 0
      ;;
    "")
      echo "ERROR: --emit-schema requires a name (frontmatter|agent-contract)" >&2
      exit 1
      ;;
    *)
      echo "ERROR: unknown schema name '${2}'. Expected: frontmatter|agent-contract" >&2
      exit 1
      ;;
  esac
fi

# Default flag values
CHECK_ID_FILENAME=true
CHECK_DEPENDS_ON=true
CHECK_TOUCHES_PATHS=true
CHECK_EXIT_COVERAGE=true
STRICT_DEPENDS=false
SHELLCHECK_EVALS=false
DRY_RUN_EVAL=false
WRITE_STATE=true
VALIDATOR_VERSION="2"

# Parse flags
ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --strict-depends) STRICT_DEPENDS=true; shift ;;
    --skip-id-filename) CHECK_ID_FILENAME=false; shift ;;
    --skip-depends-on) CHECK_DEPENDS_ON=false; shift ;;
    --skip-touches-paths) CHECK_TOUCHES_PATHS=false; shift ;;
    --skip-exit-coverage) CHECK_EXIT_COVERAGE=false; shift ;;
    --shellcheck-evals) SHELLCHECK_EVALS=true; shift ;;
    --dry-run-eval) DRY_RUN_EVAL=true; shift ;;
    --no-state) WRITE_STATE=false; shift ;;
    --) shift; ARGS+=("$@"); break ;;
    -*)
      echo "Unknown option: $1" >&2
      echo "Usage: validate-task-spec.sh [options] <path/to/T-*.md>" >&2
      exit 1
      ;;
    *) ARGS+=("$1"); shift ;;
  esac
done

if [[ ${#ARGS[@]} -eq 0 ]]; then
  echo "Usage: validate-task-spec.sh [options] <path/to/T-*.md>" >&2
  exit 1
fi

FILE="${ARGS[0]}"

if [[ ! -f "$FILE" ]]; then
  echo "FAIL: $FILE not found" >&2
  exit 1
fi

ERRORS=()
WARNINGS=()

# Check 1: frontmatter present
if ! head -1 "$FILE" | grep -q '^---$'; then
  ERRORS+=("missing YAML frontmatter opener (line 1 must be '---')")
fi

# Determine format_version (default 0 if missing)
FORMAT_VERSION=$(grep '^format_version:' "$FILE" | head -1 | awk '{print $2}' || true)
if [[ -z "$FORMAT_VERSION" ]]; then
  FORMAT_VERSION="0"
fi

# Determine profile (C2). Absent → standard (backward-compatible default). The
# profile axis is ORTHOGONAL to format_version: it scales which zones are
# REQUIRED, scaling rigor with effort/blast-radius. ts_profile() in _lib.sh is
# the single source of truth.
PROFILE="$(ts_profile "$FILE")"
DECLARED_PROFILE=$(grep -m1 '^profile:' "$FILE" | awk '{print $2}' || true)
if [[ -n "$DECLARED_PROFILE" && ! " $TS_PROFILES " == *" $DECLARED_PROFILE "* ]]; then
  ERRORS+=("profile must be one of: $TS_PROFILES (got: '$DECLARED_PROFILE')")
fi

# Extract frontmatter for mechanical checks
FRONTMATTER=$(ts_frontmatter "$FILE")

# Resolve repo root for path lookups
GIT_ROOT=$(cd "$(dirname "$FILE")" && git rev-parse --show-toplevel 2>/dev/null || echo "")
if [[ -z "$GIT_ROOT" ]]; then
  GIT_ROOT=$(dirname "$FILE")
fi
FILE_DIR=$(dirname "$FILE")

# Helper: parse a YAML list (inline [a, b] or block - a) from frontmatter
parse_yaml_list() {
  local key="$1"
  local block="$2"
  local line
  line=$(echo "$block" | grep "^${key}:" | head -1 || true)
  if [[ -z "$line" ]]; then
    return 0
  fi
  if echo "$line" | grep -qE '\['; then
    local result
    result=$(echo "$line" | sed -n 's/.*\[\(.*\)\].*/\1/p' | tr ',' '\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' || true)
    echo "$result" | grep -v '^$' || true
  elif echo "$line" | grep -qE "^${key}:[[:space:]]*$"; then
    echo "$block" | sed -n "/^${key}:/,/^[^ #]/p" | tail -n +2 | sed '/^[^ ]/d' | sed 's/^[[:space:]]*-[[:space:]]*//' | grep -v '^$' || true
  fi
  return 0
}

# Check 2: required frontmatter fields
for field in id title status effort budget_iterations agent depends_on touches_paths source_note created; do
  if ! grep -q "^${field}:" "$FILE"; then
    if [[ "$FORMAT_VERSION" == "0" ]]; then
      WARNINGS+=("missing frontmatter field (legacy v0): ${field}")
    else
      ERRORS+=("missing required frontmatter field: ${field}")
    fi
  fi
done

# Check 2b: optional v1.1 frontmatter fields (accepted if present, no error if missing)
for field in owner priority severity due_date precondition; do
  if grep -q "^${field}:" "$FILE"; then
    case "$field" in
      priority)
        PRIORITY=$(grep "^priority:" "$FILE" | head -1 | awk '{print $2}' || true)
        if [[ -n "$PRIORITY" && "$PRIORITY" != "(none)" && ! "$PRIORITY" =~ ^P[0-4]$ ]]; then
          WARNINGS+=("priority should be P0-P4 or (none) (got: '$PRIORITY')")
        fi
        ;;
      severity)
        SEVERITY=$(grep "^severity:" "$FILE" | head -1 | awk '{print $2}' || true)
        if [[ -n "$SEVERITY" && "$SEVERITY" != "(none)" && ! "$SEVERITY" =~ ^(cosmetic|refactor|feature|bugfix|security|financial-critical)$ ]]; then
          WARNINGS+=("severity should be one of: cosmetic|refactor|feature|bugfix|security|financial-critical or (none) (got: '$SEVERITY')")
        fi
        ;;
      due_date)
        DUE_DATE=$(grep "^due_date:" "$FILE" | head -1 | awk '{print $2}' || true)
        if [[ -n "$DUE_DATE" && "$DUE_DATE" != "(none)" && ! "$DUE_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
          WARNINGS+=("due_date should be YYYY-MM-DD or (none) (got: '$DUE_DATE')")
        fi
        ;;
    esac
  fi
done

# Check 2c: pipeline-orchestration fields (Canonical Build Pipeline — all optional)
#   execution_backend routes the Execute stage; signed_off is the autonomy contract.
# execution_backend is an OPEN STRING (C9): it names the canonical executor, but
# the format is vendor-neutral — any harness may be named. The validator only
# requires a non-empty, single-token value (a recognized name routes a bundled
# dispatch recipe; an unrecognized one is a custom adapter, see
# runbooks/dispatch-recipes/custom.md). Known names are listed for authoring
# convenience, NOT enforced.
if grep -q "^execution_backend:" "$FILE"; then
  EXEC_BACKEND=$(grep "^execution_backend:" "$FILE" | head -1 | awk '{print $2}' || true)
  if [[ -z "$EXEC_BACKEND" || "$EXEC_BACKEND" == "(none)" ]]; then
    WARNINGS+=("execution_backend is empty; use 'any' or name a specific executor (open string — claude|kimi|cursor|codex|<your-harness>)")
  elif [[ ! "$EXEC_BACKEND" =~ ^[A-Za-z0-9_.-]+$ ]]; then
    WARNINGS+=("execution_backend should be a single token naming an executor (got: '$EXEC_BACKEND')")
  fi
fi
if grep -q "^signed_off:" "$FILE"; then
  SIGNED_OFF=$(grep "^signed_off:" "$FILE" | head -1 | awk '{print $2}' || true)
  if [[ -n "$SIGNED_OFF" && ! "$SIGNED_OFF" =~ ^(true|false)$ ]]; then
    WARNINGS+=("signed_off must be true or false (got: '$SIGNED_OFF')")
  fi
  # A signed_off task should record who and when — warn if the audit trail is incomplete.
  if [[ "$SIGNED_OFF" == "true" ]]; then
    SO_BY=$(grep "^signed_off_by:" "$FILE" | head -1 | awk '{print $2}' || true)
    if [[ -z "$SO_BY" || "$SO_BY" == "(none)" ]]; then
      WARNINGS+=("signed_off: true but signed_off_by is (none) — sign-off must be attributable")
    fi
  fi
fi

# Check 2d: tracker_ref receipt (Register ① backlink). OPTIONAL and vendor-neutral.
# tracker_ref is the convenience backlink written BACK into the spec by the
# task-specs-to-issues REGISTER pass after a successful upsert — never by the
# author. The idempotency KEY is the marker carried ON the issue, not this field,
# so tooling must tolerate tracker_ref being (none) (e.g. a CI run that cannot
# write back to the repo). We therefore READ LIBERAL: if present and not (none)
# it SHOULD be '<tracker>:<issue-ref>' (open-string tracker, mirroring
# execution_backend), but a malformed value WARNS rather than blocks — the field
# never gates delegation.
if grep -q '^tracker_ref:' "$FILE"; then
  TRACKER_REF=$(grep -m1 '^tracker_ref:' "$FILE" | sed -E 's/^tracker_ref:[[:space:]]*//' | sed -E 's/[[:space:]]*(#.*)?$//' || true)
  if [[ -n "$TRACKER_REF" && "$TRACKER_REF" != "(none)" ]]; then
    if ! printf '%s' "$TRACKER_REF" | grep -qE '^[A-Za-z0-9_.-]+:.+$'; then
      WARNINGS+=("tracker_ref should be '<tracker>:<issue-ref>' (e.g. linear:ENG-42, github:#42) or (none) (got: '$TRACKER_REF'). It is a convenience backlink written by Register ①; the issue marker is the real idempotency key.")
    fi
  fi
fi

# linear_ref is the DEPRECATED Linear-specific alias of tracker_ref. Still
# accepted (legacy fixtures carry `linear_ref: (none)`), but a non-empty value
# should migrate to the vendor-neutral tracker_ref.
if grep -q '^linear_ref:' "$FILE"; then
  LINEAR_REF=$(grep -m1 '^linear_ref:' "$FILE" | sed -E 's/^linear_ref:[[:space:]]*//' | sed -E 's/[[:space:]]*(#.*)?$//' || true)
  if [[ -n "$LINEAR_REF" && "$LINEAR_REF" != "(none)" ]]; then
    WARNINGS+=("linear_ref is the deprecated Linear-specific field; migrate to the vendor-neutral tracker_ref (e.g. tracker_ref: linear:$LINEAR_REF)")
  fi
fi

# Check 3: effort gate (v3.4 — six-tier, tasks-all-the-way-down)
#   XS/S/M/L → runnable LEAF atoms; the write-surface must fit the tier budget.
#              L is the ceiling: accepted only on a LONG-HORIZON builder
#              (TS_LONG_HORIZON_BACKENDS) + ONE coherent done-condition.
#   XL/XXL   → decomposition NODES: NOT runnable leaves. MUST declare children:
#              (>=2 for XL, >=3 for XXL). No SDD escape — tasks decompose into tasks.
# Legacy v0 keeps the old lenient behavior (warns, never hard-fails).
EFFORT=$(grep '^effort:' "$FILE" | head -1 | awk '{print $2}' || true)
EXEC_BACKEND=$(grep '^execution_backend:' "$FILE" | head -1 | awk '{print $2}' || true)
CHILDREN=$(parse_yaml_list "children" "$FRONTMATTER")
N_CHILDREN=$(echo "$CHILDREN" | grep -c . || true); N_CHILDREN="${N_CHILDREN//[^0-9]/}"; N_CHILDREN="${N_CHILDREN:-0}"
# write-surface = |touches_paths ∪ creates_paths| (unique, ignoring the (none) sentinel)
WS_ALL=$(printf '%s\n%s\n' "$(parse_yaml_list "touches_paths" "$FRONTMATTER")" "$(parse_yaml_list "creates_paths" "$FRONTMATTER")" \
         | grep -v '^$' | grep -vxF '(none)' | sort -u || true)  # || true: a node with no write surface must not abort set -e
N_WRITES=$(echo "$WS_ALL" | grep -c . || true); N_WRITES="${N_WRITES//[^0-9]/}"; N_WRITES="${N_WRITES:-0}"

if ! ts_size_is_valid "$EFFORT"; then
  ERRORS+=("effort must be one of $TS_SIZES (got: '$EFFORT'). See references/concepts/effort-gate.md")
elif ts_size_is_leaf "$EFFORT"; then
  # LEAF — blast-radius budget on the write surface (a breach = coarse decomposition)
  MAXW=$(ts_size_writes_max "$EFFORT")
  if [[ "$N_WRITES" -gt "$MAXW" ]]; then
    WARNINGS+=("effort '$EFFORT' is a LEAF declaring $N_WRITES write path(s) (tier budget: <= $MAXW). Mis-sized — split into smaller atoms or reclassify UP; budgets expose coarse decomposition. See references/concepts/effort-gate.md")
  fi
  if [[ "$N_CHILDREN" -gt 0 ]]; then
    WARNINGS+=("effort '$EFFORT' is a runnable LEAF but declares children: — only XL/XXL nodes decompose. Drop children, or reclassify to XL/XXL.")
  fi
  if [[ "$EFFORT" == "L" ]]; then
    if [[ "$FORMAT_VERSION" == "0" ]]; then
      WARNINGS+=("effort is 'L' (legacy v0 tolerated); an L leaf is accepted only on a long-horizon builder ($TS_LONG_HORIZON_BACKENDS) and with ONE coherent done-condition.")
    elif ts_backend_is_long_horizon "$EXEC_BACKEND"; then
      WARNINGS+=("effort 'L' — accepted for the '$EXEC_BACKEND' backend (a long-horizon builder). An L leaf MUST carry ONE coherent done-condition; multiple independent evals => decompose into XS/S/M atoms. See references/concepts/effort-gate.md")
    else
      ERRORS+=("effort 'L' requires a LONG-HORIZON builder (one of: $TS_LONG_HORIZON_BACKENDS; got '${EXEC_BACKEND:-<none>}'). Name one, extend the set with TASKSPEC_LONG_HORIZON_BACKENDS, or decompose into XS/S/M atoms. See references/concepts/effort-gate.md")
    fi
  fi
else
  # NODE (XL/XXL) — a decomposition directive, never a runnable leaf. No route out.
  MINC=$(ts_size_min_children "$EFFORT")
  if [[ "$N_CHILDREN" -lt "$MINC" ]]; then
    ERRORS+=("effort '$EFFORT' is a decomposition NODE, not a runnable Task-Spec: it MUST declare children: with >= $MINC child task-spec id(s) (the vertical slices it expands into). Tasks decompose into tasks — there is no route out to SDD. See references/concepts/effort-gate.md")
  else
    WARNINGS+=("effort '$EFFORT' is a NODE with $N_CHILDREN child task-spec(s) — a composition unit, not directly delegated. A worker dispatches its children (leaves) and composes their results back up.")
  fi
fi

# Check 4: status is valid enum
STATUS=$(grep '^status:' "$FILE" | head -1 | awk '{print $2}' || true)
case "$STATUS" in
  ready|in-progress|blocked|done|parked) ;;
  *) ERRORS+=("status must be one of: ready|in-progress|blocked|done|parked (got: '$STATUS')") ;;
esac

# Check 5: id matches format T-YYYYMMDD-<slug>
ID=$(grep '^id:' "$FILE" | head -1 | awk '{print $2}' || true)
if ! echo "$ID" | grep -qE '^T-[0-9]{8}-[a-z0-9]+(-[a-z0-9]+)*$'; then
  ERRORS+=("id must match T-YYYYMMDD-<kebab-slug> (got: '$ID')")
fi

# Check 6: core zones present — PROFILE-AWARE (C2).
# The minimal contract (every profile, every non-v0 version): Goal + Success
# Criteria + Exit Check. That is the irreducible self-verifying unit.
grep -q '^## Goal' "$FILE" || ERRORS+=("Zone 1 missing: ## Goal section")
grep -qi '^## Success criteria' "$FILE" || ERRORS+=("Zone 2 missing: ## Success Criteria section")

if [[ "$FORMAT_VERSION" != "0" ]]; then
  grep -q '^## Validation Card' "$FILE" || ERRORS+=("Zone 2 missing: ## Validation Card section")
  grep -q '^## Exit Check' "$FILE" || ERRORS+=("Zone 2 missing: ## Exit Check section")

  # Context + Guardrails (Anti-Patterns, Do-Not-Touch) + Operations (Open
  # Questions) are REQUIRED for standard/full, OPTIONAL for lite. A lite spec is
  # the irreducible self-verifying unit for low-blast-radius S work; it earns its
  # smaller surface by declaring `profile: lite`.
  if [[ "$PROFILE" != "lite" ]]; then
    grep -q '^## Context' "$FILE" || ERRORS+=("Zone 1 missing: ## Context section (required for profile: $PROFILE; use profile: lite to omit)")
    grep -qi '^## Anti-Patterns' "$FILE" || ERRORS+=("Zone 5 missing: ## Anti-Patterns section (required for profile: $PROFILE)")
    grep -qi '^## Do-Not-Touch' "$FILE" || grep -qi '^## Do-not-touch' "$FILE" || ERRORS+=("Zone 5 missing: ## Do-Not-Touch section (required for profile: $PROFILE)")
    grep -qi '^## Open Questions' "$FILE" || ERRORS+=("Zone 6 missing: ## Open Questions section (required for profile: $PROFILE)")
  fi
fi

# Check 6b: six-zone sections (Behavior + Rollback + Observability), profile-scaled.
#   - Behavior: a v3 concept. Required for v3 standard/full (the BDD layer +
#     traceability anchor), optional for lite. v2/v1 specs predate it — never
#     required there (backward compatibility).
#   - Rollback + Observability: required for FULL (unattended dispatch needs a
#     reversal path and runtime expectations); recommended-not-required otherwise.
if [[ "$FORMAT_VERSION" != "0" ]]; then
  if [[ "$FORMAT_VERSION" == "3" && "$PROFILE" != "lite" ]]; then
    grep -q '^## Behavior' "$FILE" || ERRORS+=("Behavior section missing: ## Behavior with Given/When/Then B-N scenarios (required for v3 profile: $PROFILE; use profile: lite to omit)")
  fi
  if [[ "$PROFILE" == "full" ]]; then
    grep -qi '^## Rollback' "$FILE" || ERRORS+=("## Rollback Plan section required for profile: full (use '(none — additive)' as the body if truly not applicable)")
    grep -qi '^## Observability' "$FILE" || ERRORS+=("## Observability Hooks section required for profile: full")
  else
    grep -qi '^## Rollback' "$FILE" || WARNINGS+=("six-zone format recommends a ## Rollback Plan section (use '(none — additive)' if not applicable)")
    grep -qi '^## Observability' "$FILE" || WARNINGS+=("six-zone format recommends an ## Observability Hooks section (use '(none)' if not applicable)")
  fi
fi

# Check 7: eval functions
if ! grep -qE '^eval_[0-9]+\(\)' "$FILE"; then
  if [[ "$FORMAT_VERSION" == "0" ]]; then
    WARNINGS+=("no eval_N() bash functions found (legacy v0 uses markdown checklists); run migrate-legacy-task.sh to upgrade")
  else
    ERRORS+=("no eval_N() bash functions found in Success Criteria")
  fi
fi

# Check 8: validation_card YAML
if ! grep -q 'success_criteria:' "$FILE"; then
  if [[ "$FORMAT_VERSION" == "0" ]]; then
    WARNINGS+=("validation_card YAML missing (legacy v0); run migrate-legacy-task.sh to upgrade")
  else
    ERRORS+=("validation_card YAML missing success_criteria list")
  fi
fi

if [[ "$FORMAT_VERSION" != "0" ]]; then
  if ! grep -q 'retry_policy:' "$FILE"; then
    ERRORS+=("validation_card YAML missing retry_policy")
  fi
  if ! grep -q 'agent_contract:' "$FILE"; then
    ERRORS+=("validation_card YAML missing agent_contract")
  fi
fi

# Check 8c: check_type discipline (SOTA — deterministic vs llm_judge).
# check_type is optional (absent = deterministic). When present it must be a known
# value; llm_judge criteria require a judge_prompt; a spec that is majority
# llm_judge is likely misfiled SDD work and earns a warning.
if grep -qE '^[[:space:]]*check_type:' "$FILE"; then
  BAD_CT=$(grep -E '^[[:space:]]*check_type:' "$FILE" | awk '{print $2}' | grep -vE '^(deterministic|llm_judge)$' || true)
  if [[ -n "$BAD_CT" ]]; then
    ERRORS+=("check_type must be 'deterministic' or 'llm_judge' (got: '$(echo "$BAD_CT" | head -1)')")
  fi
  LLM_COUNT=$(grep -cE '^[[:space:]]*check_type:[[:space:]]*llm_judge' "$FILE" || true)
  LLM_COUNT=${LLM_COUNT//[^0-9]/}
  CT_TOTAL=$(grep -cE '^[[:space:]]*check_type:' "$FILE" || true)
  CT_TOTAL=${CT_TOTAL//[^0-9]/}
  if [[ "${LLM_COUNT:-0}" -gt 0 ]]; then
    # Every llm_judge criterion needs a judge_prompt somewhere in the card.
    if ! grep -qE '^[[:space:]]*judge_prompt:' "$FILE"; then
      ERRORS+=("a criterion declares check_type: llm_judge but no judge_prompt is provided")
    fi
    # Majority-llm_judge smell: likely subjective/SDD work, not EDD.
    if [[ "${CT_TOTAL:-0}" -gt 0 && $((LLM_COUNT * 2)) -gt "$CT_TOTAL" ]]; then
      WARNINGS+=("majority of success_criteria are llm_judge ($LLM_COUNT/$CT_TOTAL); this may be subjective SDD work misfiled as EDD")
    fi
  fi
fi

# Check 8b: agent_contract schema validation (v2 strict, v1 warns)
if grep -q 'agent_contract:' "$FILE"; then
  # Extract agent_contract block (from the key to the closing ``` of the yaml block)
  AC_BLOCK=$(sed -n '/^agent_contract:/,/^```/p' "$FILE" | sed '$d')

  # v2 and v3 share the agent_contract v2 schema (v3 is additive at the spec level,
  # not the contract level). Both demand the strict machine schema below.
  if [[ "$FORMAT_VERSION" == "2" || "$FORMAT_VERSION" == "3" ]]; then
    # v2/v3: version required
    if ! echo "$AC_BLOCK" | grep -qE '^  version:[[:space:]]*2'; then
      ERRORS+=("agent_contract version: 2 is required for format_version: $FORMAT_VERSION")
    fi

    # v2: produce must be a YAML list. BOTH styles are valid YAML and accepted:
    #   block:  produce:\n    - code        inline-flow:  produce: [code]
    # A pipe-delimited scalar (v1 legacy) or a bare scalar is rejected.
    PRODUCE_LINE=$(echo "$AC_BLOCK" | grep -E '^  produce:' | head -1 || true)
    if echo "$PRODUCE_LINE" | grep -qE 'produce:[[:space:]]*\[' ; then
      # Inline-flow list — must be non-empty.
      if echo "$PRODUCE_LINE" | grep -qE 'produce:[[:space:]]*\[[[:space:]]*\]'; then
        ERRORS+=("agent_contract produce inline list is empty")
      fi
    elif echo "$PRODUCE_LINE" | grep -qE 'produce:[[:space:]]*[^[:space:]]'; then
      if echo "$PRODUCE_LINE" | grep -q '|'; then
        ERRORS+=("agent_contract produce is a pipe-delimited string (v1 legacy); v2 requires a YAML list")
      else
        ERRORS+=("agent_contract produce must be a YAML list (v2 format), not a scalar string")
      fi
    else
      # Block-style list — ensure at least one list item exists under produce
      if ! echo "$AC_BLOCK" | awk '/^  produce:/{flag=1; next} /^  [a-z_]+:/{flag=0} flag && /^    - /{found=1} END{exit !found}'; then
        ERRORS+=("agent_contract produce must be a non-empty YAML list")
      fi
    fi

    # v2: emit must be a YAML list with valid enum values (block OR inline-flow).
    EMIT_LINE=$(echo "$AC_BLOCK" | grep -E '^  emit:' | head -1 || true)
    if echo "$EMIT_LINE" | grep -qE 'emit:[[:space:]]*\[' ; then
      # Inline-flow list — extract bracketed values and validate the enum.
      EMIT_VALUES=$(echo "$EMIT_LINE" | sed -n 's/.*\[\(.*\)\].*/\1/p' | tr ',' '\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | grep -v '^$' || true)
      if [[ -z "$EMIT_VALUES" ]]; then
        ERRORS+=("agent_contract emit inline list is empty")
      else
        for val in $EMIT_VALUES; do
          case "$val" in
            pass|fail|retry_with_reason|parked_with_context) ;;
            *) ERRORS+=("agent_contract emit contains invalid value: '$val'") ;;
          esac
        done
      fi
    elif echo "$EMIT_LINE" | grep -qE 'emit:[[:space:]]*[^[:space:]]'; then
      if echo "$EMIT_LINE" | grep -q '|'; then
        ERRORS+=("agent_contract emit is a pipe-delimited string (v1 legacy); v2 requires a YAML list")
      else
        ERRORS+=("agent_contract emit must be a YAML list (v2 format), not a scalar string")
      fi
    else
      EMIT_VALUES=$(echo "$AC_BLOCK" | awk '/^  emit:/{flag=1; next} /^  [a-z_]+:/{flag=0} flag && /^    - /{print $2}')
      if [[ -z "$EMIT_VALUES" ]]; then
        ERRORS+=("agent_contract emit must be a non-empty YAML list")
      else
        for val in $EMIT_VALUES; do
          case "$val" in
            pass|fail|retry_with_reason|parked_with_context) ;;
            *) ERRORS+=("agent_contract emit contains invalid value: '$val'") ;;
          esac
        done
      fi
    fi

    # v2: timeout_minutes required, integer, 1-1440
    TIMEOUT=$(echo "$AC_BLOCK" | grep -E '^  timeout_minutes:' | head -1 | awk '{print $2}' || true)
    if [[ -z "$TIMEOUT" ]]; then
      ERRORS+=("agent_contract timeout_minutes is required (v2)")
    elif ! [[ "$TIMEOUT" =~ ^[0-9]+$ ]]; then
      ERRORS+=("agent_contract timeout_minutes must be an integer (got: '$TIMEOUT')")
    elif [[ "$TIMEOUT" -lt 1 || "$TIMEOUT" -gt 1440 ]]; then
      ERRORS+=("agent_contract timeout_minutes must be between 1 and 1440 (got: '$TIMEOUT')")
    fi

    # v2: sandbox_type required, enum
    SANDBOX=$(echo "$AC_BLOCK" | grep -E '^  sandbox_type:' | head -1 | awk '{print $2}' || true)
    if [[ -z "$SANDBOX" ]]; then
      ERRORS+=("agent_contract sandbox_type is required (v2)")
    elif [[ "$SANDBOX" != "host" && "$SANDBOX" != "isolated" && "$SANDBOX" != "ephemeral" ]]; then
      ERRORS+=("agent_contract sandbox_type must be host|isolated|ephemeral (got: '$SANDBOX')")
    fi

    # v2: required_tools required and non-empty
    if ! echo "$AC_BLOCK" | grep -qE '^  required_tools:'; then
      ERRORS+=("agent_contract required_tools is required (v2)")
    else
      RT_LINE=$(echo "$AC_BLOCK" | grep -E '^  required_tools:' | head -1 || true)
      if echo "$RT_LINE" | grep -qE 'required_tools:[[:space:]]*$'; then
        # Block list — look for items
        if ! echo "$AC_BLOCK" | awk '/^  required_tools:/{flag=1; next} /^  [a-z_]+:/{flag=0} flag && /^    - /{found=1} END{exit !found}'; then
          ERRORS+=("agent_contract required_tools must be a non-empty list")
        fi
      else
        # Inline list [a, b] — check not empty
        if echo "$RT_LINE" | grep -qE 'required_tools:[[:space:]]*\[[[:space:]]*\]'; then
          ERRORS+=("agent_contract required_tools must be a non-empty list")
        fi
      fi
    fi

  elif [[ "$FORMAT_VERSION" == "1" ]]; then
    # v1 legacy warnings (warn, don't fail)
    if echo "$AC_BLOCK" | grep -qE '^  produce:.*\|'; then
      WARNINGS+=("agent_contract uses v1 pipe-delimited produce; consider migrating to v2 YAML list")
    fi
    if echo "$AC_BLOCK" | grep -qE '^  emit:.*\|'; then
      WARNINGS+=("agent_contract uses v1 pipe-delimited emit; consider migrating to v2 YAML list")
    fi
    if ! echo "$AC_BLOCK" | grep -qE '^  version:'; then
      WARNINGS+=("agent_contract missing version; v2 recommends version: 2")
    fi
  fi
fi

# Check 8d: behavior <-> eval TRACEABILITY (C4 — the bidirectional-coverage lint).
# This is the chain that turns five stapled sections into a machine-checked spec:
#   - every behavior B-N must be verified by >= 1 eval (no orphan behavior), AND
#   - every eval's `verifies:` must reference a DEFINED behavior (no orphan ref).
# A v3 concept: enforced for v3 standard/full (where ## Behavior is required).
# Skipped for lite (behavior implied by evals) and for v2/v1/v0 (predate behaviors).
if [[ "$FORMAT_VERSION" == "3" && "$PROFILE" != "lite" ]]; then
  DECLARED_B=$(ts_behavior_ids "$FILE")
  VERIFIED_B=$(ts_verified_behavior_ids "$FILE")

  if [[ -z "$DECLARED_B" ]]; then
    ERRORS+=("profile: $PROFILE requires >= 1 behavior scenario (B-N) in the ## Behavior section")
  fi

  # Orphan behaviors: declared but no eval verifies them.
  for b in $DECLARED_B; do
    if ! echo "$VERIFIED_B" | grep -qx "$b"; then
      ERRORS+=("behavior $b is declared but no eval 'verifies:' it — every behavior needs >= 1 mapped eval (traceability)")
    fi
  done

  # Orphan verifies-refs: an eval references a behavior id that is not declared.
  for b in $VERIFIED_B; do
    if ! echo "$DECLARED_B" | grep -qx "$b"; then
      ERRORS+=("an eval 'verifies: [$b]' but $b is not declared in the ## Behavior section (dangling reference)")
    fi
  done

  # Every deterministic eval should map to a behavior. An eval with no `verifies:`
  # at all (when behaviors exist) is a coverage hole — warn so the author either
  # maps it or downgrades to lite.
  if [[ -n "$DECLARED_B" ]]; then
    SC_EVAL_IDS=$(awk '/^## Success Criteria/{f=1; next} /^## /{f=0} f' "$FILE" | grep -oE 'eval_[0-9]+\(\)' | sed 's/()//' | sort -u || true)
    CARD_VERIFIES_PRESENT=$(grep -cE '^[[:space:]]*verifies:' "$FILE" || true)
    CARD_VERIFIES_PRESENT="${CARD_VERIFIES_PRESENT//[^0-9]/}"
    CARD_VERIFIES_PRESENT="${CARD_VERIFIES_PRESENT:-0}"
    N_EVALS=$(echo "$SC_EVAL_IDS" | grep -c . || true)
    N_EVALS="${N_EVALS//[^0-9]/}"
    N_EVALS="${N_EVALS:-0}"
    if [[ "$N_EVALS" -gt 0 && "$CARD_VERIFIES_PRESENT" -lt "$N_EVALS" ]]; then
      WARNINGS+=("$((N_EVALS - CARD_VERIFIES_PRESENT)) eval(s) have no 'verifies:' mapping in the Validation Card — map them to a behavior or use profile: lite")
    fi
  fi
fi

# Check 8e: parent reference (C5). PRD/SDD altitude is REFERENCED, never embedded.
# If a parent is declared and is a repo-relative path, it should resolve. A url
# (off-repo) is accepted as-is. Absent/(none) is fine — not every task decomposes
# from a parent doc.
PARENT_REF=$(grep -m1 '^parent:' "$FILE" | sed -E 's/^parent:[[:space:]]*//' | sed -E 's/[[:space:]]*(#.*)?$//' || true)
if [[ -n "$PARENT_REF" && "$PARENT_REF" != "(none)" ]]; then
  if [[ "$PARENT_REF" != http*://* && "$PARENT_REF" != /* ]]; then
    if [[ ! -e "$GIT_ROOT/$PARENT_REF" && ! -e "$FILE_DIR/$PARENT_REF" ]]; then
      WARNINGS+=("parent references a path that does not resolve: '$PARENT_REF' (PRD/SDD should be referenced, not embedded — fix the link)")
    fi
  fi
fi

# Check 9: no leftover placeholders
# Self-fix (WS4): the previous form used `grep -c X file 2>/dev/null || echo 0`
# which is the same inverted-grep-c pattern Check 16 below catches. Use ${var:-0}
# normalisation instead so this script doesn't trip its own lint.
PLACEHOLDER_COUNT=$(grep -c '{{TODO' "$FILE" 2>/dev/null) || true
PLACEHOLDER_COUNT="${PLACEHOLDER_COUNT:-0}"
PLACEHOLDER_COUNT="${PLACEHOLDER_COUNT//[^0-9]/}"
PLACEHOLDER_COUNT="${PLACEHOLDER_COUNT:-0}"
if [[ "$PLACEHOLDER_COUNT" -gt 0 ]]; then
  ERRORS+=("$PLACEHOLDER_COUNT unfilled {{TODO}} placeholder(s) remain")
fi
if grep -qE '\{\{[A-Z_]+\}\}' "$FILE"; then
  ERRORS+=("unfilled {{PLACEHOLDER}} strings detected")
fi

# Check 10: id matches filename basename
if [[ "$CHECK_ID_FILENAME" == true && -n "$ID" ]]; then
  BASENAME=$(basename "$FILE" .md)
  if [[ "$ID" != "$BASENAME" ]]; then
    ERRORS+=("id ('$ID') does not match filename basename ('$BASENAME')")
  fi
fi

# Check 11: depends_on references exist
if [[ "$CHECK_DEPENDS_ON" == true && -n "$FRONTMATTER" ]]; then
  DEPS=$(parse_yaml_list "depends_on" "$FRONTMATTER")
  for dep in $DEPS; do
    found=false
    dep_status=""
    # The lifecycle sub-directories must be resolved RELATIVE TO THE SPEC, not
    # only under $GIT_ROOT/tasks. In the cvg/ layout a spec lives at
    # <project>/cvg/tasks/, so its done/ sibling is "$FILE_DIR/done" while
    # "$GIT_ROOT/tasks/done" does not exist — the error message claimed to have
    # searched done/ and never had. The first task to FINISH therefore made every
    # dependent spec unvalidatable, and re-sealing an amended one impossible.
    #
    # Same root cause as the workspace-root and register-KNOWN fixes: a path
    # derived from an assumed layout instead of from the file in hand. GIT_ROOT
    # entries are kept so the flat layout keeps working.
    for dir in "$FILE_DIR" \
               "$FILE_DIR/queue" "$FILE_DIR/archive" "$FILE_DIR/feature" "$FILE_DIR/done" "$FILE_DIR/parked" \
               "$GIT_ROOT/tasks" "$GIT_ROOT/tasks/queue" "$GIT_ROOT/tasks/archive" "$GIT_ROOT/tasks/feature" "$GIT_ROOT/tasks/done" "$GIT_ROOT/tasks/parked"; do
      if [[ -f "$dir/${dep}.md" ]]; then
        found=true
        dep_status=$(grep '^status:' "$dir/${dep}.md" 2>/dev/null | head -1 | awk '{print $2}' || true)
        break
      fi
    done
    if [[ "$found" != true ]]; then
      ERRORS+=("depends_on references non-existent task: '$dep' (searched tasks/, queue/, archive/, feature/, done/, parked/)")
    elif [[ "$dep_status" == "parked" || "$dep_status" == "done" ]]; then
      if [[ "$STRICT_DEPENDS" == true ]]; then
        ERRORS+=("depends_on references $dep_status task: '$dep' (--strict-depends)")
      else
        WARNINGS+=("depends_on references $dep_status task: '$dep'")
      fi
    fi
  done
fi

# Check 12: touches_paths exist on disk
# Greenfield tasks declare files they CREATE via the optional `creates_paths:` list;
# those entries are exempt from the existence check (they do not exist yet — that is
# the point). `touches_paths` is for files being MODIFIED, which must already exist.
if [[ "$CHECK_TOUCHES_PATHS" == true && -n "$FRONTMATTER" ]]; then
  CREATES=$(parse_yaml_list "creates_paths" "$FRONTMATTER")
  TOUCHES=$(parse_yaml_list "touches_paths" "$FRONTMATTER")
  for tp in $TOUCHES; do
    # Skip entries also declared in creates_paths (a file may be created here and
    # legitimately not exist yet even if redundantly listed under touches_paths)
    if echo "$CREATES" | grep -qxF "$tp"; then
      continue
    fi
    if [[ "$tp" == /* ]]; then
      full_path="$tp"
    else
      full_path="$GIT_ROOT/$tp"
    fi
    if [[ ! -e "$full_path" ]]; then
      if [[ "$STATUS" == "parked" ]]; then
        WARNINGS+=("touches_paths entry does not exist: '$tp' (task is parked)")
      else
        ERRORS+=("touches_paths entry does not exist: '$tp' (if this task CREATES it, declare it under creates_paths instead)")
      fi
    fi
  done
fi

# Check 13: Exit Check calls every defined eval
if [[ "$CHECK_EXIT_COVERAGE" == true && "$FORMAT_VERSION" != "0" ]]; then
  SC_SECTION=$(awk '/^## Success Criteria/{found=1; next} /^## /{found=0} found' "$FILE" || true)
  DEFINED_EVALS=$(echo "$SC_SECTION" | grep -oE 'eval_[0-9]+\(\)' | sed 's/()//' | sort -u || true)

  EC_SECTION=$(awk '/^## Exit Check/{found=1; next} /^## /{found=0} found' "$FILE" || true)
  CALLED_EVALS=$(echo "$EC_SECTION" | grep -oE 'eval_[0-9]+' | sort -u || true)

  for ev in $DEFINED_EVALS; do
    if ! echo "$CALLED_EVALS" | grep -qx "$ev"; then
      WARNINGS+=("$ev is defined in Success Criteria but not called in Exit Check")
    fi
  done
fi

# Check 14: shellcheck eval bodies
if [[ "$SHELLCHECK_EVALS" == true ]]; then
  if ! command -v shellcheck >/dev/null 2>&1; then
    ERRORS+=("shellcheck not installed (required for --shellcheck-evals)")
  else
    SC_SECTION=$(awk 'tolower($0) ~ /^## success criteria$/ {found=1; next} tolower($0) ~ /^## / {found=0} found' "$FILE" || true)
    SC_BASH=$(echo "$SC_SECTION" | awk '/^```bash$/{in_block=1; next} /^```$/{in_block=0} in_block' || true)
    EC_SECTION=$(awk 'tolower($0) ~ /^## exit check$/ {found=1; next} tolower($0) ~ /^## / {found=0} found' "$FILE" || true)
    EC_BASH=$(echo "$EC_SECTION" | awk '/^```bash$/{in_block=1; next} /^```$/{in_block=0} in_block' || true)

    if [[ -n "$SC_BASH" ]]; then
      tmp_script=$(mktemp -t task-spec-shellcheck-XXXXXX.sh)
      {
        echo '#!/usr/bin/env bash'
        echo "$SC_BASH"
        echo "$EC_BASH"
      } > "$tmp_script"

      shellcheck_output=$(shellcheck -e SC2034 "$tmp_script" 2>&1) || {
        sc_summary=$(echo "$shellcheck_output" | head -30)
        ERRORS+=("shellcheck found issues in eval bodies:
$sc_summary")
      }
      rm -f "$tmp_script"
    fi
  fi
fi

# Check 15: dry-run evals in subshell
if [[ "$DRY_RUN_EVAL" == true ]]; then
  SC_SECTION=$(awk 'tolower($0) ~ /^## success criteria$/ {found=1; next} tolower($0) ~ /^## / {found=0} found' "$FILE" || true)
  SC_BASH=$(echo "$SC_SECTION" | awk '/^```bash$/{in_block=1; next} /^```$/{in_block=0} in_block' || true)
  EC_SECTION=$(awk 'tolower($0) ~ /^## exit check$/ {found=1; next} tolower($0) ~ /^## / {found=0} found' "$FILE" || true)
  EC_BASH=$(echo "$EC_SECTION" | awk '/^```bash$/{in_block=1; next} /^```$/{in_block=0} in_block' || true)

  if [[ -n "$SC_BASH" && -n "$EC_BASH" ]]; then
    tmp_script=$(mktemp -t task-spec-dryrun-XXXXXX.sh)
    {
      echo "$SC_BASH"
      echo "$EC_BASH"
    } > "$tmp_script"

    dry_run_output=$(bash "$tmp_script" 2>&1) || {
      dry_run_err=$(echo "$dry_run_output" | tail -10)
      ERRORS+=("dry-run eval failed in subshell: $dry_run_err")
    }
    rm -f "$tmp_script"
  fi
fi

# Check 16: inverted-eval lint on eval bodies (v2.1.1 — generic umbrella rule)
# Detects anti-patterns where bash exits 0 on the success-wanted path via
# substitution-with-fallback followed by numeric tests on non-normalised values.
# Each pattern can be opted out per line via an allowlist marker on the
# immediately preceding line.
#
# Allowlist legend:
#   # task-spec:allow-grep-c-fallback              — skip grep -c friendly fast-path on this line
#   # task-spec:allow-wc-fallback                  — skip wc friendly fast-path on this line
#   # task-spec:allow-exit-status-as-count         — skip 'echo $?' anti-pattern on this line
#   # task-spec:allow-substitution-with-true-fallback — skip the legacy v2.1 `$(...) || true` rule on this line
#   # task-spec:allow-numeric-fallback             — skip the v2.1.1 umbrella rule on this line
#                                                    (covers any $(...) OR `...` followed by
#                                                     '|| (true|echo <integer>)' followed within
#                                                     4 lines by a non-normalised numeric test)
#
# Patterns covered:
#   1+2. $(grep -c X file [2>/dev/null] || echo 0|true)  — friendly: allow-grep-c-fallback
#   3.   $(wc -X [...] || echo 0|true)                   — friendly: allow-wc-fallback
#   4.   grep -c X file ; echo $?                        — marker: allow-exit-status-as-count
#   5.   multi-line (handled by --dry-run-eval integer assertion — not a regex)
#   6.   UMBRELLA: $(...) OR `...` followed by '|| (true|echo <integer>)' followed
#        within 4 lines by a numeric -eq/-ne/-lt/-le/-gt/-ge test against a bare
#        variable that is NOT normalised via '${var:-0}' or '${var//[^0-9]/}'.
#        Marker: allow-numeric-fallback (umbrella) OR
#        allow-substitution-with-true-fallback (legacy, '|| true' form only).
#
# Self-fix: validate-task-spec.sh's own PLACEHOLDER_COUNT computation was rewritten
# above to use ${var:-0} normalisation so this check does not trip on its own script.

# Pre-compile regex literals (bash =~ parses each operand and complex parens
# inside literal regexes can trip the parser; assigning to a variable is the
# canonical workaround).
re_grep_c_fb='\$\(.*grep[[:space:]]+-c[^)]*\|\|[[:space:]]*(echo[[:space:]]+0|true)'
re_wc_fb='\$\(.*wc[[:space:]]+-[lcwm][^)]*\|\|[[:space:]]*(echo[[:space:]]+0|true)'
re_grep_c_echodollar='grep[[:space:]]+-c[^;]*;[[:space:]]*echo[[:space:]]+\$\?'
re_subst_true='\$\(.*\)[[:space:]]*\|\|[[:space:]]*true'
# Umbrella: $(...) OR `...` substitution paired with '|| (true|echo <integer>)'.
# Two forms:
#   external: $(...)  || (true|echo N)   — `||` outside the substitution
#   internal: $( ... || (true|echo N) )  — `||` inside the substitution (most
#                                          common with grep -c/awk/jq/python)
re_subst_numeric_fallback_external='(\$\(.*\)|`[^`]*`)[[:space:]]*\|\|[[:space:]]*(true|echo[[:space:]]+-?[0-9]+)'
re_subst_numeric_fallback_internal='(\$\(|`).*\|\|[[:space:]]*(true|echo[[:space:]]+-?[0-9]+).*(\)|`)'
re_numeric_cmp_zero='"?\$\{?[A-Za-z_][A-Za-z0-9_]*\}?"?[[:space:]]+-(eq|ne|lt|le|gt|ge)[[:space:]]+0'
re_normalised_var=':-0\}|//\[\^0-9\]/'

INVERTED_GREP_HITS=()
# Extract eval bash blocks locally if not already populated by --shellcheck-evals
# or --dry-run-eval. Check 16 must run on the default validate invocation, not
# only on opt-in.
if [[ -z "${SC_BASH:-}" ]]; then
  _SC_SECTION_L16=$(awk '/^## Success Criteria/{found=1; next} /^## /{found=0} found' "$FILE" 2>/dev/null || true)
  SC_BASH=$(echo "$_SC_SECTION_L16" | awk '/^```bash$/{in_block=1; next} /^```$/{in_block=0} in_block' 2>/dev/null || true)
fi
if [[ -z "${EC_BASH:-}" ]]; then
  _EC_SECTION_L16=$(awk '/^## Exit Check/{found=1; next} /^## /{found=0} found' "$FILE" 2>/dev/null || true)
  EC_BASH=$(echo "$_EC_SECTION_L16" | awk '/^```bash$/{in_block=1; next} /^```$/{in_block=0} in_block' 2>/dev/null || true)
fi

if [[ -n "${SC_BASH:-}" || -n "${EC_BASH:-}" ]]; then
  EVAL_BLOCK="${SC_BASH:-}
${EC_BASH:-}"

  prev_line=""
  while IFS= read -r line; do
    # Allowlist marker on PREVIOUS line skips this line's check
    if [[ "$prev_line" == *"# task-spec:allow-grep-c-fallback"* ]] && [[ "$line" =~ $re_grep_c_fb ]]; then
      prev_line="$line"; continue
    fi
    if [[ "$prev_line" == *"# task-spec:allow-wc-fallback"* ]] && [[ "$line" =~ $re_wc_fb ]]; then
      prev_line="$line"; continue
    fi
    if [[ "$prev_line" == *"# task-spec:allow-exit-status-as-count"* ]] && [[ "$line" =~ $re_grep_c_echodollar ]]; then
      prev_line="$line"; continue
    fi
    # The legacy 'allow-substitution-with-true-fallback' and the new umbrella
    # 'allow-numeric-fallback' both suppress the umbrella rule below. The
    # legacy marker only covers the '|| true' form; the umbrella marker covers
    # both '|| true' and '|| echo <integer>'.
    umbrella_match=false
    if [[ "$line" =~ $re_subst_numeric_fallback_external ]] || [[ "$line" =~ $re_subst_numeric_fallback_internal ]]; then
      umbrella_match=true
    fi
    umbrella_suppressed=false
    if [[ "$prev_line" == *"# task-spec:allow-numeric-fallback"* ]] && [[ "$umbrella_match" == true ]]; then
      umbrella_suppressed=true
    fi
    if [[ "$prev_line" == *"# task-spec:allow-substitution-with-true-fallback"* ]] && [[ "$line" =~ $re_subst_true ]]; then
      umbrella_suppressed=true
    fi

    # Friendly per-command fast-paths (only emitted when umbrella would fire on
    # this line; they give a more specific remediation hint).
    if [[ "$line" =~ $re_grep_c_fb ]]; then
      INVERTED_GREP_HITS+=("inverted grep -c pattern: '$line' — use '! grep -q PATTERN file' instead, or annotate with '# task-spec:allow-grep-c-fallback'")
    elif [[ "$line" =~ $re_wc_fb ]]; then
      INVERTED_GREP_HITS+=("inverted wc fallback: '$line' — normalise with ': \"\${var:=0}\"' before numeric compare, or annotate with '# task-spec:allow-wc-fallback'")
    elif [[ "$line" =~ $re_grep_c_echodollar ]]; then
      INVERTED_GREP_HITS+=("captures exit status, not match count: '$line' — use '\$(grep -c PATTERN file)' alone, or annotate with '# task-spec:allow-exit-status-as-count'")
    elif [[ "$umbrella_suppressed" == false ]] && [[ "$umbrella_match" == true ]]; then
      # Umbrella rule: substitution-with-fallback (any command, $(...) or
      # backticks, '|| true' or '|| echo <integer>') followed within 4 lines by
      # a numeric test against a non-normalised variable.
      following=$(echo "$EVAL_BLOCK" | grep -A4 -F "$line" 2>/dev/null | head -5)
      if [[ "$following" =~ $re_numeric_cmp_zero ]] && [[ ! "$following" =~ $re_normalised_var ]]; then
        INVERTED_GREP_HITS+=("substitution-with-fallback followed by numeric test without integer normalisation: '$line' — normalise the captured value with '\${var:-0}' before comparing, or annotate with '# task-spec:allow-numeric-fallback'")
      fi
    fi

    prev_line="$line"
  done <<< "$EVAL_BLOCK"
fi

if [[ ${#INVERTED_GREP_HITS[@]} -gt 0 ]]; then
  for hit in "${INVERTED_GREP_HITS[@]}"; do
    ERRORS+=("$hit")
  done
fi

# Check 16b: existence-only evals (the stub loophole)
#
# An eval that only asserts a file EXISTS — plus greps for a keyword in it —
# cannot tell a real implementation from a three-line stub. `test -f x.py &&
# grep -q assert x.py` is satisfied by `echo "# assert" > x.py`. The loop then
# goes green, the receipt says pass, and nothing was built.
#
# This is the reward-hacking failure mode that matters most, because unlike an
# inverted grep it is not a mistake — it is what an eval degrades INTO when the
# author cannot run the real thing yet.
#
# Detection: the eval block contains a file-existence test, and contains NO
# command that executes anything the task produced. Emitted as a WARNING here
# (a supervised task may legitimately be file-shaped — an ADR, a doc, a config)
# and escalated to a BLOCK by safe-to-delegate.sh, which is the gate that
# actually claims a task is safe to run unsupervised.
#
# Opt out per spec with: # task-spec:allow-existence-only
re_existence_test='test[[:space:]]+-[fde][[:space:]]|\[[[:space:]]+-[fde][[:space:]]'
re_executes='python3?[[:space:]]|pytest|psql|sqlite3|docker[[:space:]]|curl[[:space:]]|node[[:space:]]|npm[[:space:]]|go[[:space:]]+(test|run)|cargo[[:space:]]|make[[:space:]]|bash[[:space:]]+[^-]|sh[[:space:]]+[^-]|dbt[[:space:]]|\./'
EXISTENCE_ONLY=false
if [[ -n "${SC_BASH:-}" ]] && ! grep -q 'task-spec:allow-existence-only' "$FILE" 2>/dev/null; then
  if [[ "$SC_BASH" =~ $re_existence_test ]] && [[ ! "$SC_BASH" =~ $re_executes ]]; then
    EXISTENCE_ONLY=true
    WARNINGS+=("existence-only evals: every check asserts a file EXISTS but nothing RUNS what the task produced — a stub file satisfies this spec. Make at least one eval execute the artifact, or annotate the spec with '# task-spec:allow-existence-only' if the deliverable really is a document.")
  fi
fi

# Check 17: sign-off envelope on signed_off (structural floor + B2 HMAC, v2.2)
#
# STRUCTURAL FLOOR (unchanged from v2.1.1): signed_off: true REQUIRES both
# signed_off_by (non-empty, non-'(none)') and signed_off_at (ISO-8601). This
# catches *accidental* hand-stamping and always holds regardless of crypto.
#
# B2 HMAC THREE-TIER DEGRADE (v2.2), keyed on key+sig presence:
#   TIER 1 — key present + signed_off_sig present + MAC verifies → full crypto
#            trust, no error (exit 0).
#   TIER 2 — key MISSING (fresh clone / no env var / no crypto binary) OR
#            signed_off_sig absent entirely (legacy v2.1.1 spec) → structural-
#            only with a LOUD warning on stdout, exit 0. NEVER hard-fail just
#            because there is no key.
#   TIER 3 — key present but MAC MISMATCH, or signed_off_sig malformed → hard
#            FAIL (exit 1): "DO NOT DELEGATE: spec body or envelope modified
#            after stamping".
#
# The MAC covers the CANONICAL payload (id + body_digest + the three signed_off*
# VALUES), computed by ts_signoff_payload in _lib.sh. String comparison is used
# (acceptable for v2.2 — a future hardening could add a constant-time compare;
# the secret here is repo-shared, not per-request, so timing leakage is not the
# threat). See references/concepts/signed-off.md.
#
# This check ONLY fires when signed_off has been set to true. signed_off: false
# is the default and requires no envelope.
SIGNED_OFF_RAW=$(grep -m1 '^signed_off:' "$FILE" 2>/dev/null | awk -F: '{print $2}' | xargs || true)
SIGNED_OFF_RAW="${SIGNED_OFF_RAW:-}"
if [[ "$SIGNED_OFF_RAW" == "true" ]]; then
  SIGNED_BY=$(grep -m1 '^signed_off_by:' "$FILE" 2>/dev/null | sed -E 's/^signed_off_by:[[:space:]]*//' || true)
  SIGNED_BY="${SIGNED_BY:-}"
  SIGNED_AT=$(grep -m1 '^signed_off_at:' "$FILE" 2>/dev/null | sed -E 's/^signed_off_at:[[:space:]]*//' || true)
  SIGNED_AT="${SIGNED_AT:-}"

  STRUCTURAL_FLOOR_OK=true
  if [[ -z "$SIGNED_BY" || "$SIGNED_BY" == "(none)" ]]; then
    ERRORS+=("signed_off: true but signed_off_by is empty or (none) — hand-stamping detected. The autonomy contract is produced ONLY by safe-to-delegate.sh --stamp. Run: bash $(dirname "${BASH_SOURCE[0]}")/safe-to-delegate.sh --stamp $FILE")
    STRUCTURAL_FLOOR_OK=false
  fi
  if [[ -z "$SIGNED_AT" || "$SIGNED_AT" == "(none)" ]]; then
    ERRORS+=("signed_off: true but signed_off_at is empty or (none) — hand-stamping detected. The autonomy contract is produced ONLY by safe-to-delegate.sh --stamp. Run: bash $(dirname "${BASH_SOURCE[0]}")/safe-to-delegate.sh --stamp $FILE")
    STRUCTURAL_FLOOR_OK=false
  elif ! [[ "$SIGNED_AT" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z?$ ]]; then
    ERRORS+=("signed_off_at must be ISO-8601 (got: '$SIGNED_AT') — hand-stamping suspected. Re-run safe-to-delegate.sh --stamp.")
    STRUCTURAL_FLOOR_OK=false
  fi

  # B2 crypto tiers run only when the structural floor held (no point checking a
  # MAC on a spec that already failed for missing _by/_at).
  if [[ "$STRUCTURAL_FLOOR_OK" == true ]]; then
    SIGNED_SIG=$(grep -m1 '^signed_off_sig:' "$FILE" 2>/dev/null | sed -E 's/^signed_off_sig:[[:space:]]*//' || true)
    SIGNED_SIG="${SIGNED_SIG:-}"
    set +e
    SIGN_KEY="$(ts_resolve_signing_key "$FILE" 2>/dev/null)"
    set -e

    if [[ -z "$SIGN_KEY" ]]; then
      # TIER 2: no key (fresh clone / no env var). Structural-only. Loud + exit 0.
      echo "WARN(Tier 2): $FILE — no signing key resolved; sign-off is structural-only (Tier 2). Supervised dispatch only; NOT eligible for unsupervised crank. Set TASKSPEC_SIGNING_KEY or run configs/setup-taskspec-signing-key.sh for Tier 1 crypto trust."
    elif [[ -z "$SIGNED_SIG" ]]; then
      # TIER 2: key present but no sig field (legacy v2.1.1 spec). Structural-only.
      echo "WARN(Tier 2): $FILE — signed_off_sig absent (legacy/structural-only sign-off). Re-stamp with safe-to-delegate.sh --stamp under a key for Tier 1 crypto trust. Supervised dispatch only."
    elif ! [[ "$SIGNED_SIG" =~ ^hmac-sha256-v[12]:[0-9a-zA-Z]+:[0-9a-f]+$ ]]; then
      # TIER 3: sig field malformed.
      ERRORS+=("DO NOT DELEGATE: signed_off_sig is malformed (got: '$SIGNED_SIG'); expected hmac-sha256-v2:<keyid>:<hex>. Spec body or envelope modified after stamping. Re-run safe-to-delegate.sh --stamp.")
    else
      set +e
      EXPECTED_SIG="$(ts_compute_signoff_sig "$FILE" "$SIGN_KEY")"
      ESIG_RC=$?
      set -e
      if [[ $ESIG_RC -ne 0 || -z "$EXPECTED_SIG" ]]; then
        # Key present but no crypto provider to recompute → degrade to Tier 2.
        echo "WARN(Tier 2): $FILE — signing key present but no sha256 provider (openssl/shasum/sha256sum) to verify the MAC; sign-off is structural-only (Tier 2). Supervised dispatch only."
      elif [[ "$EXPECTED_SIG" == "$SIGNED_SIG" ]]; then
        # TIER 1: full crypto trust.
        echo "OK(Tier 1): $FILE — signed_off_sig HMAC verified (full crypto trust)."
      elif [[ "$SIGNED_SIG" == hmac-sha256-v1:* ]]; then
        # A v1 envelope predates authorization sealing: it never covered write
        # scope, dependencies, budgets, or routing. Verify it on its own terms —
        # authentic means Tier 2 (supervised), NOT a forgery.
        set +e
        LEGACY_SIG="$(ts_compute_signoff_sig "$FILE" "$SIGN_KEY" v1)"
        set -e
        if [[ -n "$LEGACY_SIG" && "$LEGACY_SIG" == "$SIGNED_SIG" ]]; then
          echo "WARN(Tier 2): $FILE — legacy envelope v1: authentic, but write scope, dependencies, budgets and routing were NOT sealed. Re-stamp with safe-to-delegate.sh --stamp for Tier 1."
        else
          ERRORS+=("DO NOT DELEGATE: spec body or envelope modified after stamping — signed_off_sig HMAC mismatch. Re-run safe-to-delegate.sh --stamp to re-seal.")
        fi
      else
        # TIER 3: MAC mismatch — body OR an authorization field changed.
        ERRORS+=("DO NOT DELEGATE: spec body, authorization fields (touches_paths/creates_paths/depends_on/effort/backend/agent/budgets/requires), or envelope modified after stamping — signed_off_sig HMAC mismatch. Re-run safe-to-delegate.sh --stamp to re-seal.")
      fi
    fi
  fi
fi

# Check 19: acceptance envelope floor (C7). `accepted: true` is the POST-execution
# contract written ONLY by accept-task.sh; it requires accepted_by + accepted_at,
# and acceptance presupposes sign-off. Hand-setting `accepted: true` is rejected
# the same way hand-stamping signed_off is.
ACCEPTED_RAW=$(grep -m1 '^accepted:' "$FILE" 2>/dev/null | awk -F: '{print $2}' | xargs || true)
if [[ "$STATUS" == "done" && "${ACCEPTED_RAW:-}" != "true" ]]; then
  ERRORS+=("status: done requires accepted: true — accept and settle the task before moving it into done/")
fi
if [[ "${ACCEPTED_RAW:-}" == "true" ]]; then
  ACC_BY=$(grep -m1 '^accepted_by:' "$FILE" 2>/dev/null | sed -E 's/^accepted_by:[[:space:]]*//' || true)
  ACC_AT=$(grep -m1 '^accepted_at:' "$FILE" 2>/dev/null | sed -E 's/^accepted_at:[[:space:]]*//' || true)
  if [[ -z "$ACC_BY" || "$ACC_BY" == "(none)" ]]; then
    ERRORS+=("accepted: true but accepted_by is empty or (none) — acceptance is produced ONLY by accept-task.sh. Run: bash $(dirname "${BASH_SOURCE[0]}")/accept-task.sh $FILE")
  fi
  if [[ -z "$ACC_AT" || "$ACC_AT" == "(none)" ]]; then
    ERRORS+=("accepted: true but accepted_at is empty or (none) — acceptance is produced ONLY by accept-task.sh.")
  elif ! [[ "$ACC_AT" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z?$ ]]; then
    ERRORS+=("accepted_at must be ISO-8601 (got: '$ACC_AT')")
  fi
  if [[ "${SIGNED_OFF_RAW:-}" != "true" ]]; then
    ERRORS+=("accepted: true but signed_off is not true — a task cannot be accepted before it is signed off (gate → dispatch → accept ordering)")
  fi
fi
if [[ "$STATUS" == "done" ]]; then
  WORKSPACE_ROOT="$(ts_workspace_root "$FILE")"
  RECEIPT="$WORKSPACE_ROOT/cvg/receipts/${ID}.json"
  if [[ ! -f "$RECEIPT" ]]; then
    ERRORS+=("status: done requires a passing execution receipt at cvg/receipts/${ID}.json")
  elif ! python3 - "$RECEIPT" "$ID" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    receipt = json.load(handle)
assert receipt.get("task_id") == sys.argv[2]
assert receipt.get("result") == "pass"
PY
  then
    ERRORS+=("status: done receipt must be valid JSON with matching task_id and result: pass")
  fi
fi

# Report
if [[ ${#ERRORS[@]} -gt 0 ]]; then
  echo "FAIL: $FILE has ${#ERRORS[@]} validation error(s):"
  for err in "${ERRORS[@]}"; do
    echo "  - $err"
  done
  if [[ ${#WARNINGS[@]} -gt 0 ]]; then
    echo "Warnings:"
    for warn in "${WARNINGS[@]}"; do
      echo "  - $warn"
    done
  fi
  exit 1
fi

# --- State writer (only on successful validation, unless --no-state) ---
if [[ "$WRITE_STATE" == true ]]; then
  STATE_DIR="$(ts_backlog_root "$FILE")"
  TASKSPEC_BACKLOG_DIR="$STATE_DIR" \
    TASKSPEC_STATE_GENERATOR="validate-task-spec.sh" \
    TASKSPEC_STATE_VALIDATOR_VERSION="$VALIDATOR_VERSION" \
    bash "$TASKSPEC_SKILL_DIR/scripts/rebuild-state.sh" >/dev/null
fi

if [[ ${#WARNINGS[@]} -gt 0 ]]; then
  if [[ "$FORMAT_VERSION" == "0" ]]; then
    echo "WARN: $FILE is a legacy Task-Spec (format_version: 0). Accepted under layered policy with ${#WARNINGS[@]} warning(s):"
  else
    echo "WARN: $FILE has ${#WARNINGS[@]} validation warning(s):"
  fi
  for warn in "${WARNINGS[@]}"; do
    echo "  - $warn"
  done
  exit 0
fi

A2A_STATE="$(ts_a2a_state "$STATUS")"
echo "OK: $FILE is a valid Task-Spec v${FORMAT_VERSION:-1} (profile: $PROFILE, status: $STATUS → A2A: $A2A_STATE)"
exit 0
