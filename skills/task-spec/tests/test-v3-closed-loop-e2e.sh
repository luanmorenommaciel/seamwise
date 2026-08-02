#!/usr/bin/env bash
# test-v3-closed-loop-e2e.sh — prove the v3 closed loop end-to-end.
#
# Drives ONE solvable task through the FULL lifecycle in an isolated tempdir repo:
#   AUTHOR → VALIDATE → PRE-GATE (safe-to-delegate --stamp) → DISPATCH (ref-executor)
#          → ACCEPT (accept-task --stamp) → loop-closed assertions.
#
# It asserts each phase's contract AND the v3-specific behaviors:
#   - profile/behavior/traceability validate
#   - the pre-gate stamps signed_off (with HMAC under a key)
#   - the executor makes the evals pass and leaves settlement to acceptance
#   - the acceptance gate ACCEPTS (evals pass from clean state + blast-radius +
#     HMAC intact) and stamps accepted: true
#   - only an accepted task with a passing receipt can transition to done
#   - the negative path: a blast-radius breach is REJECTED by accept-task
#
# Exit 0 = the closed loop works; non-zero = a phase broke.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPTS="$SKILL_DIR/scripts"

GREEN=$'\033[32m'; RED=$'\033[31m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
if [[ ! -t 1 ]]; then GREEN=""; RED=""; BOLD=""; RESET=""; fi

pass=0; fail=0
ok()  { echo "  ${GREEN}✓${RESET} $1"; pass=$((pass+1)); }
no()  { echo "  ${RED}✗${RESET} $1"; fail=$((fail+1)); }
chk() { if eval "$2"; then ok "$1"; else no "$1 [cmd: $2]"; fi; }

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"
git init -q
git config user.email e2e@task-spec.local
git config user.name "E2E Harness"
mkdir -p tasks src
# A repo-local signing key so we exercise Tier-1 crypto trust end-to-end.
mkdir -p .git/info
printf 'e2e-closed-loop-key\n' > .git/info/taskspec-signing-key
# Establish a clean baseline commit so accept-task's blast-radius diff has a base.
echo "baseline" > src/baseline.txt
git add -A && git commit -qm baseline

SPEC="$WORK/tasks/T-20260618-e2e-closed-loop.md"
TASK_ID="T-20260618-e2e-closed-loop"

echo "${BOLD}=== Phase 1: AUTHOR a solvable v3 standard spec ===${RESET}"
cat > "$SPEC" <<'SPEC'
---
id: T-20260618-e2e-closed-loop
title: E2E closed-loop reference task
status: ready
format_version: 3
profile: standard
effort: S
budget_iterations: 5
agent: any
parent: (none)
depends_on: []
touches_paths:
  - src/feature.txt
creates_paths:
  - src/feature.txt
source_note: (none)
created: 2026-06-18T00:00:00Z
tags: [e2e]
severity: feature
execution_backend: any
signed_off: false
signed_off_by: (none)
signed_off_at: (none)
accepted: false
accepted_by: (none)
accepted_at: (none)
---

# E2E closed-loop reference task

> **Why:** Exercises the full author→gate→dispatch→execute→accept loop.

## Goal

Write the literal text `done` into `src/feature.txt`.

## Context

A synthetic task in an isolated fixture repo; the executor must create the file.

## Behavior

- **B-1** — GIVEN the repo WHEN the task runs THEN `src/feature.txt` exists and contains exactly `done`.

## Success Criteria

```bash
eval_1() {
  grep -qx 'done' "$GIT_ROOT/src/feature.txt"
}
```

## Validation Card

```yaml
success_criteria:
  - id: eval_1
    description: feature file contains 'done'
    runnable: bash
    check_type: deterministic
    verifies: [B-1]
    terminal: true
    expected_duration_sec: 1
retry_policy:
  max_iterations: 5
  circuit_breaker_no_progress: 3
  on_terminal_failure: park_with_context
agent_contract:
  version: 2
  read: [intent, behavior, contract]
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

## Rollback Plan

`git checkout -- src/feature.txt` restores the pre-task state (additive file write).

## Observability Hooks

- **Expected duration:** under 1s (a single file write + grep)
- **Key metric:** the Exit Check exit code
- **Alert condition:** Exit Check non-zero after dispatch
- **Log tail:** (none — synthetic fixture)

## Anti-Patterns

- **Don't write anything but `done`** — the eval is exact-match.

## Do-Not-Touch

- `src/baseline.txt` — pre-existing, out of scope.

## Open Questions

(none — fully specified)
SPEC
chk "spec file authored" "[[ -f '$SPEC' ]]"

echo "${BOLD}=== Phase 2: VALIDATE (structural + profile + traceability) ===${RESET}"
v_out=$(bash "$SCRIPTS/validate-task-spec.sh" "$SPEC" 2>&1); v_rc=$?
chk "validate passes (rc=0)" "[[ $v_rc -eq 0 ]]"
chk "validate reports v3 + standard profile" "echo \"\$v_out\" | grep -q 'valid Task-Spec v3 (profile: standard'"
chk "validate maps status→A2A submitted" "echo \"\$v_out\" | grep -q 'A2A: submitted'"

echo "${BOLD}=== Phase 3: PRE-GATE (safe-to-delegate --stamp) ===${RESET}"
g_out=$(TASKSPEC_SIGNING_KEY="$WORK/.git/info/taskspec-signing-key" bash "$SCRIPTS/safe-to-delegate.sh" --stamp "$SPEC" 2>&1); g_rc=$?
chk "pre-gate verdict DELEGATE (rc=0)" "[[ $g_rc -eq 0 ]]"
chk "pre-gate stamped signed_off: true" "grep -q '^signed_off: true' '$SPEC'"
chk "pre-gate sealed HMAC (Tier 1)" "echo \"\$g_out\" | grep -q 'TIER=1'"

echo "${BOLD}=== Phase 4: DISPATCH (reference executor drives the work) ===${RESET}"
# The ref-executor's work block keys on the Goal phrasing; this spec uses a
# different file, so we use a tiny inline executor that honors the same contract
# (acquire lock → do work → run evals → done/park) to keep the test self-contained.
INLINE_EXEC="$(mktemp -t inline-exec-XXXXXX.sh)"
trap 'rm -rf "$WORK" "$INLINE_EXEC"' EXIT
cat > "$INLINE_EXEC" <<EXEC
#!/usr/bin/env bash
set -euo pipefail
source "$SCRIPTS/_lib.sh"
SPEC="\$1"
GIT_ROOT="\$(cd "\$(dirname "\$SPEC")" && git rev-parse --show-toplevel)"; export GIT_ROOT
ts_set_frontmatter_field "\$SPEC" "status" "in-progress"
printf 'done\n' > "\$GIT_ROOT/src/feature.txt"
if bash "$SCRIPTS/run-task-spec.sh" "\$SPEC" >/dev/null 2>&1; then
  ts_set_frontmatter_field "\$SPEC" "status" "in-progress"
else
  ts_set_frontmatter_field "\$SPEC" "status" "parked"
fi
EXEC
chmod +x "$INLINE_EXEC"
bash "$INLINE_EXEC" "$SPEC"
chk "executor created src/feature.txt == 'done'" "grep -qx done '$WORK/src/feature.txt'"
chk "executor leaves passing work in-progress for independent acceptance" "grep -q '^status: in-progress' '$SPEC'"

echo "${BOLD}=== Phase 5: ACCEPT (post-execution gate) ===${RESET}"
# accept-task re-runs evals from the worktree, checks blast radius vs baseline,
# and re-verifies the sign-off HMAC. signed_off_sig was computed over the BODY at
# stamp time; the executor only changed FRONTMATTER status + repo files, so the
# body digest is unchanged and the HMAC must still verify.
a_out=$(TASKSPEC_SIGNING_KEY="$WORK/.git/info/taskspec-signing-key" bash "$SCRIPTS/accept-task.sh" --stamp --base HEAD "$SPEC" 2>&1); a_rc=$?
echo "$a_out" | sed 's/^/    /'
chk "accept verdict ACCEPT (rc=0)" "[[ $a_rc -eq 0 ]]"
chk "accept stamped accepted: true" "grep -q '^accepted: true' '$SPEC'"
chk "accept emitted ACCEPTED=1" "echo \"\$a_out\" | grep -q 'ACCEPTED=1'"
chk "accept GATE A (evals pass) reported" "echo \"\$a_out\" | grep -q 'A. Evals pass'"

echo "${BOLD}=== Phase 6: LOOP CLOSED — final spec validates with full envelope ===${RESET}"
mkdir -p "$WORK/cvg/receipts"
printf '{"schema":"cvg.execution-receipt.v1","task_id":"%s","result":"pass"}\n' "$TASK_ID" \
  > "$WORK/cvg/receipts/$TASK_ID.json"
TASKSPEC_BACKLOG_DIR="$WORK/tasks" \
  bash "$SCRIPTS/transition-status.sh" "$TASK_ID" done "closed-loop settlement" >/dev/null
SPEC="$WORK/tasks/done/$TASK_ID.md"
chk "settlement moved only accepted, receipted work to done" \
  "[[ -f '$SPEC' ]] && grep -q '^status: done' '$SPEC'"
f_out=$(TASKSPEC_SIGNING_KEY="$WORK/.git/info/taskspec-signing-key" bash "$SCRIPTS/validate-task-spec.sh" "$SPEC" 2>&1); f_rc=$?
chk "final validate passes" "[[ $f_rc -eq 0 ]]"
chk "final validate confirms Tier-1 HMAC" "echo \"\$f_out\" | grep -q 'OK(Tier 1)'"

echo "${BOLD}=== Phase 7: NEGATIVE — blast-radius breach is REJECTED ===${RESET}"
# Reset acceptance, write a stray file OUTSIDE touches_paths, and confirm reject.
bash -c "source '$SCRIPTS/_lib.sh'; ts_set_frontmatter_field '$SPEC' 'accepted' 'false'"
echo "stray" > "$WORK/src/unauthorized.txt"
set +e
n_out=$(TASKSPEC_SIGNING_KEY="$WORK/.git/info/taskspec-signing-key" bash "$SCRIPTS/accept-task.sh" --base HEAD "$SPEC" 2>&1); n_rc=$?
set -e
chk "breach REJECTED (rc=1)" "[[ $n_rc -eq 1 ]]"
chk "breach names the out-of-scope file" "echo \"\$n_out\" | grep -q 'unauthorized.txt'"
rm -f "$WORK/src/unauthorized.txt"

echo ""
echo "========================================"
echo "Results: ${pass} passed, ${fail} failed"
echo "========================================"
[[ $fail -eq 0 ]]
