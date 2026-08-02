#!/usr/bin/env bash
# conformance-check.sh — certify that an EXECUTOR honors the Task-Spec contract (C8).
#
# safe-to-delegate certifies a SPEC; this certifies a CONSUMER. It is how the
# claim "any conformant executor can pick it up" becomes TESTABLE instead of
# aspirational (the METR lesson: a standard wins on its conformance suite +
# adapters, not its prose).
#
# Conformance levels (cumulative):
#   L0 — Reads the format and runs the evals. The executor, given a signed spec,
#        must produce work that makes the Exit Check return 0. (Minimum bar: a
#        plain bash loop qualifies.)
#   L1 — L0 + honors the LIFECYCLE: acquires a lock (status → in-progress) before
#        working and releases it (status → done) on success, via the status
#        transitions the format defines.
#   L2 — L1 + honors the RETRY BUDGET: on a spec it cannot satisfy within
#        budget_iterations, it stops and parks (status → parked) with a reason
#        rather than looping forever.
#
# The executor under test is any command that takes a spec path as its last arg
# and drives it to completion (mutating the repo + the spec's status). A trivial
# conformant reference executor ships at scripts/ref-executor.sh for self-test.
#
# Usage:
#   bash conformance-check.sh --level L0|L1|L2 --executor "<cmd>" [--keep]
#   bash conformance-check.sh --self-test            # run against the bundled ref executor
#
# The candidate command is invoked as:  <cmd> <spec-path>
#
# Exit codes:
#   0 — CONFORMANT at the requested level
#   1 — NON-CONFORMANT (a required behavior was not observed)
#   2 — usage / harness error

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "$SCRIPT_DIR/_lib.sh"
ts_version_flag "$@"

LEVEL=""
EXECUTOR=""
KEEP=false
SELF_TEST=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --level)    LEVEL="${2:-}"; shift 2 ;;
    --executor) EXECUTOR="${2:-}"; shift 2 ;;
    --keep)     KEEP=true; shift ;;
    --self-test) SELF_TEST=true; shift ;;
    --help|-h)  grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)          echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ "$SELF_TEST" == true ]]; then
  EXECUTOR="bash $SCRIPT_DIR/ref-executor.sh"
  [[ -z "$LEVEL" ]] && LEVEL="L2"
fi
if [[ -z "$LEVEL" || -z "$EXECUTOR" ]]; then
  echo "Usage: conformance-check.sh --level L0|L1|L2 --executor \"<cmd>\"   (or --self-test)" >&2
  exit 2
fi
case "$LEVEL" in L0|L1|L2) ;; *) echo "level must be L0|L1|L2 (got: $LEVEL)" >&2; exit 2 ;; esac

GREEN=$'\033[32m'; RED=$'\033[31m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
if [[ ! -t 1 ]]; then GREEN=""; RED=""; BOLD=""; RESET=""; fi

# --- Build an isolated conformance fixture repo (a real git repo in a tempdir) ---
WORK=$(mktemp -d)
cleanup() { [[ "$KEEP" == true ]] || rm -rf "$WORK"; }
trap cleanup EXIT
if [[ "$KEEP" == true ]]; then echo "fixture repo: $WORK (kept)"; fi

cd "$WORK"
git init -q
git config user.email conformance@task-spec.local
git config user.name "Conformance Harness"
mkdir -p tasks src

# status_of <spec> → current frontmatter status
status_of() { grep -m1 '^status:' "$1" | awk '{print $2}'; }

# A SOLVABLE reference spec: the eval passes once src/marker.txt contains "done".
write_solvable_spec() {
  local f="$1"
  cat > "$f" <<'SPEC'
---
id: T-20260618-conformance-solvable
title: Conformance solvable reference
status: ready
format_version: 3
profile: lite
effort: S
budget_iterations: 5
agent: any
depends_on: []
touches_paths:
  - src/marker.txt
source_note: (none)
created: 2026-06-18T00:00:00Z
tags: []
execution_backend: any
signed_off: true
signed_off_by: conformance-harness
signed_off_at: 2026-06-18T00:00:00Z
---

# Conformance solvable reference

> **Why:** Drives the executor through the happy path.

## Goal

Write the literal text `done` into `src/marker.txt`.

## Success Criteria

```bash
eval_1() {
  grep -qx 'done' "$GIT_ROOT/src/marker.txt"
}
```

## Validation Card

```yaml
success_criteria:
  - id: eval_1
    description: marker file contains 'done'
    runnable: bash
    check_type: deterministic
    terminal: true
    expected_duration_sec: 1
retry_policy:
  max_iterations: 5
  circuit_breaker_no_progress: 3
  on_terminal_failure: park_with_context
agent_contract:
  version: 2
  read: [intent, contract]
  produce: [code]
  required_tools: [bash]
  timeout_minutes: 5
  sandbox_type: host
  emit: [pass, fail, parked_with_context]
```

## Exit Check

```bash
eval_1
```
SPEC
}

# An UNSOLVABLE reference spec: the eval can never pass (asserts an impossible
# condition). A conformant L2 executor must PARK it, not loop forever.
write_unsolvable_spec() {
  local f="$1"
  cat > "$f" <<'SPEC'
---
id: T-20260618-conformance-unsolvable
title: Conformance unsolvable reference
status: ready
format_version: 3
profile: lite
effort: S
budget_iterations: 2
agent: any
depends_on: []
touches_paths:
  - src/marker.txt
source_note: (none)
created: 2026-06-18T00:00:00Z
tags: []
execution_backend: any
signed_off: true
signed_off_by: conformance-harness
signed_off_at: 2026-06-18T00:00:00Z
---

# Conformance unsolvable reference

> **Why:** Forces the budget/park path.

## Goal

Satisfy an impossible assertion (this task is designed to be unsatisfiable).

## Success Criteria

```bash
eval_1() {
  test -f "$GIT_ROOT/src/__never_exists__.flag"
}
```

## Validation Card

```yaml
success_criteria:
  - id: eval_1
    description: an impossible flag file exists
    runnable: bash
    check_type: deterministic
    terminal: true
    expected_duration_sec: 1
retry_policy:
  max_iterations: 2
  circuit_breaker_no_progress: 1
  on_terminal_failure: park_with_context
agent_contract:
  version: 2
  read: [intent, contract]
  produce: [code]
  required_tools: [bash]
  timeout_minutes: 5
  sandbox_type: host
  emit: [pass, fail, parked_with_context]
```

## Exit Check

```bash
eval_1
```
SPEC
}

GIT_ROOT="$WORK"; export GIT_ROOT
fails=0
report() { if [[ "$1" -eq 0 ]]; then echo "   ${GREEN}PASS${RESET} — $2"; else echo "   ${RED}FAIL${RESET} — $2"; fails=$((fails+1)); fi; }

echo "${BOLD}Conformance check — level $LEVEL — executor: $EXECUTOR${RESET}"
echo "────────────────────────────────────────────────────────"

# ===== L0: reads the format + makes the evals pass =====
SPEC="$WORK/tasks/T-20260618-conformance-solvable.md"
write_solvable_spec "$SPEC"
echo "L0. Executor drives a solvable spec to a passing Exit Check ..."
set +e
$EXECUTOR "$SPEC" >/dev/null 2>&1
bash "$SCRIPT_DIR/run-task-spec.sh" "$SPEC" >/dev/null 2>&1
l0_rc=$?
set -e
report "$l0_rc" "Exit Check passes after execution (L0: reads format, runs evals)"

# ===== L1: honors lifecycle (status → in-progress → done) =====
if [[ "$LEVEL" == "L1" || "$LEVEL" == "L2" ]]; then
  echo "L1. Executor honors the status lifecycle (→ done on success) ..."
  st=$(status_of "$SPEC")
  if [[ "$st" == "done" ]]; then report 0 "status transitioned to 'done' (A2A: $(ts_a2a_state 'done'))"; else report 1 "status is '$st', expected 'done' after success"; fi
fi

# ===== L2: honors the retry budget (parks an unsolvable spec) =====
if [[ "$LEVEL" == "L2" ]]; then
  USPEC="$WORK/tasks/T-20260618-conformance-unsolvable.md"
  write_unsolvable_spec "$USPEC"
  echo "L2. Executor parks an unsolvable spec within budget (no infinite loop) ..."
  set +e
  # shellcheck disable=SC2086
  ts_timeout 30 $EXECUTOR "$USPEC" >/dev/null 2>&1
  l2_exec_rc=$?
  set -e
  st=$(status_of "$USPEC")
  if [[ $l2_exec_rc -eq 124 ]]; then
    report 1 "executor TIMED OUT on an unsolvable spec — it does not honor budget_iterations (looped forever)"
  elif [[ "$st" == "parked" ]]; then
    report 0 "unsolvable spec parked (status: parked, A2A: $(ts_a2a_state parked)) within budget"
  else
    report 1 "unsolvable spec ended in status '$st', expected 'parked'"
  fi
fi

echo "────────────────────────────────────────────────────────"
if [[ $fails -eq 0 ]]; then
  echo "${BOLD}${GREEN}CONFORMANT${RESET} at $LEVEL — this executor honors the Task-Spec contract."
  echo "CONFORMANCE=$LEVEL"
  exit 0
else
  echo "${BOLD}${RED}NON-CONFORMANT${RESET} at $LEVEL — $fails required behavior(s) not observed."
  echo "CONFORMANCE=none"
  exit 1
fi
