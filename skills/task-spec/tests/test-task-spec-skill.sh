#!/usr/bin/env bash
# test-task-spec-skill.sh — Self-test suite for the task-spec skill
#
# Exercises the skill's toolchain end-to-end in an isolated temp directory:
#   1. generate-task-spec.sh   → create a dummy task
#   2. fill stubs              → produce a valid Task-Spec v2
#   3. validate-task-spec.sh   → expect PASS
#   4. controlled error        → expect FAIL with specific message
#   5. transition-status.sh    → ready → in-progress → done
#   6. verify file moves       → tasks/ → tasks/done/
#   7. rebuild-state.sh        → confirm _state.yaml reflects the task
#   8. list-ready.sh           → confirm done task excluded
#   9. archive.sh              → confirm no-op for already-archived
#  10. backup-backlog.sh       → confirm archive created
#
# Safe to run anytime. Does NOT write to the real tasks/ backlog.

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts" && pwd)"
FIXTURES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/fixtures" && pwd)"
PASS=0
FAIL=0

# --- Flag parsing (v2.1 — adds --suite) ---
SUITE="default"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --suite=*)
      SUITE="${1#*=}"
      shift
      ;;
    --suite)
      SUITE="${2:-default}"
      shift 2
      ;;
    --help|-h)
      sed -n '2,16p' "$0"
      echo ""
      echo "Suites:"
      echo "  default          E2E walkthrough (generate → validate → transition → ...)"
      echo "  fixtures         Inverted-grep-c + structural sign-off envelope oracle (WS5)"
      echo "  hmac             Keyed B2 HMAC sign-off envelope suite (Tier 1/2/3, v2.2)"
      echo "  bash-portability bash-3.2 version-guard checks for the aux/core scripts"
      echo "  conformance      Reference conformance driver (run_conformance.sh, self adapter)"
      echo "  all              Run all (default + fixtures + hmac + bash-portability)"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

pass() {
  echo "  ✓ $1"
  PASS=$((PASS + 1))
}

fail() {
  echo "  ✗ $1" >&2
  FAIL=$((FAIL + 1))
}

# ---------------------------------------------------------------------------
# --suite fixtures  →  oracle-driven inverted-grep + sign-off envelope assertions
# ---------------------------------------------------------------------------
run_fixtures_suite() {
  local oracle="$FIXTURES_DIR/oracle.json"
  if [[ ! -f "$oracle" ]]; then
    echo "✗ oracle.json not found at $oracle" >&2
    return 1
  fi
  echo "Suite: fixtures — running validate-task-spec.sh against $FIXTURES_DIR/*.md per oracle.json"

  # Parse oracle entries (use python3 for JSON; it ships with macOS and every Linux).
  while IFS=$'\t' read -r fixture expected_exit expected_match description; do
    [[ -z "$fixture" ]] && continue
    local fpath="$FIXTURES_DIR/$fixture"
    if [[ ! -f "$fpath" ]]; then
      fail "fixture missing: $fixture"
      continue
    fi
    set +e
    out=$(bash "$SCRIPT_DIR/validate-task-spec.sh" --skip-touches-paths --skip-id-filename "$fpath" 2>&1)
    rc=$?
    set -e
    if [[ "$rc" != "$expected_exit" ]]; then
      fail "$fixture: expected exit $expected_exit, got $rc — $description"
      continue
    fi
    if [[ -n "$expected_match" ]] && ! echo "$out" | grep -qF "$expected_match"; then
      fail "$fixture: exit $rc OK but missing '$expected_match' in output — $description"
      continue
    fi
    pass "$fixture (exit $rc, matched '$expected_match')"
  done < <(python3 -c "
import json, sys
o = json.load(open('$oracle'))
for f in o['fixtures']:
    print(f'{f[\"fixture\"]}\t{f[\"expected_exit\"]}\t{f[\"expected_match\"]}\t{f[\"description\"]}')
")
}

# ---------------------------------------------------------------------------
# --suite bash-portability  →  delegate to test-bash-portability.sh
# ---------------------------------------------------------------------------
run_bash_portability_suite() {
  local portability_test
  portability_test="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test-bash-portability.sh"
  if [[ ! -f "$portability_test" ]]; then
    fail "test-bash-portability.sh not found at $portability_test"
    return 1
  fi
  echo "Suite: bash-portability — delegating to test-bash-portability.sh"
  if bash "$portability_test"; then
    pass "bash-portability suite passed"
  else
    fail "bash-portability suite reported failures"
  fi
}

# ---------------------------------------------------------------------------
# --suite hmac  →  delegate to test-hmac-envelope.sh (keyed B2 suite)
# ---------------------------------------------------------------------------
run_hmac_suite() {
  local hmac_test
  hmac_test="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test-hmac-envelope.sh"
  if [[ ! -f "$hmac_test" ]]; then
    fail "test-hmac-envelope.sh not found at $hmac_test"
    return 1
  fi
  echo "Suite: hmac — delegating to test-hmac-envelope.sh (keyed B2 envelope)"
  if env -u TASKSPEC_SIGNING_KEY bash "$hmac_test"; then
    pass "hmac suite passed"
  else
    fail "hmac suite reported failures"
  fi
}

# ---------------------------------------------------------------------------
# --suite conformance  →  run the reference conformance driver (self adapter)
# ---------------------------------------------------------------------------
run_conformance_suite() {
  local driver
  driver="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/conformance/run_conformance.sh"
  if [[ ! -f "$driver" ]]; then
    fail "run_conformance.sh not found at $driver"
    return 1
  fi
  echo "Suite: conformance — delegating to run_conformance.sh (self adapter)"
  set +e
  bash "$driver" --adapter "$(dirname "$driver")/adapters/self.sh"
  local rc=$?
  set -e
  if [[ $rc -eq 0 ]]; then
    pass "conformance suite passed (0 non-waived failures)"
  else
    fail "conformance suite reported $rc non-waived failure(s)"
  fi
}

# Dispatch on --suite
case "$SUITE" in
  fixtures)
    run_fixtures_suite
    echo ""
    echo "========================================"
    printf "Results: %d passed, %d failed\n" "$PASS" "$FAIL"
    echo "========================================"
    [[ $FAIL -gt 0 ]] && exit 1
    exit 0
    ;;
  hmac)
    run_hmac_suite
    echo ""
    echo "========================================"
    printf "Results: %d passed, %d failed\n" "$PASS" "$FAIL"
    echo "========================================"
    [[ $FAIL -gt 0 ]] && exit 1
    exit 0
    ;;
  bash-portability)
    run_bash_portability_suite
    echo ""
    echo "========================================"
    printf "Results: %d passed, %d failed\n" "$PASS" "$FAIL"
    echo "========================================"
    [[ $FAIL -gt 0 ]] && exit 1
    exit 0
    ;;
  conformance)
    run_conformance_suite
    echo ""
    echo "========================================"
    printf "Results: %d passed, %d failed\n" "$PASS" "$FAIL"
    echo "========================================"
    [[ $FAIL -gt 0 ]] && exit 1
    exit 0
    ;;
  all)
    run_fixtures_suite
    echo ""
    run_hmac_suite
    echo ""
    run_bash_portability_suite
    echo ""
    # fall through to default body below
    ;;
  default)
    # fall through to default body below
    ;;
  *)
    echo "Unknown suite: $SUITE (use default|fixtures|hmac|bash-portability|conformance|all)" >&2
    exit 1
    ;;
esac

# ---------------------------------------------------------------------------
# Isolated workspace
# ---------------------------------------------------------------------------
TMPDIR=$(mktemp -d -t task-spec-test-XXXXXX)
export TMPDIR
trap 'rm -rf "$TMPDIR"' EXIT

cd "$TMPDIR"
git init --quiet

# macOS lacks flock(1); provide a minimal shim for isolated, single-threaded
# tests. Safe because no concurrent processes access the lock.
if ! command -v flock >/dev/null 2>&1; then
  mkdir -p "$TMPDIR/bin"
  cat > "$TMPDIR/bin/flock" <<'FLOCKSHIM'
#!/usr/bin/env bash
# Minimal flock shim for isolated test environments.
exit 0
FLOCKSHIM
  chmod +x "$TMPDIR/bin/flock"
  export PATH="$TMPDIR/bin:$PATH"
fi

# Dummy file for touches_paths validation
mkdir -p tasks
touch tasks/dummy.txt

# ---------------------------------------------------------------------------
# 1. generate-task-spec.sh
# ---------------------------------------------------------------------------
echo "=== 1. generate-task-spec.sh ==="
gen_out=$(bash "$SCRIPT_DIR/generate-task-spec.sh" test-self-test-suite S any "self-test" 2>&1)
TARGET=$(echo "$gen_out" | grep '^Spec written: ' | sed 's/^Spec written: //')
ID=$(basename "$TARGET" .md)

if [[ -f "$TARGET" ]]; then
  pass "generator created $TARGET"
else
  fail "generator did not create expected file (output: $gen_out)"
  exit 1
fi

FILE_ID=$(grep '^id:' "$TARGET" | head -1 | awk '{print $2}')
if [[ "$FILE_ID" == "$ID" ]]; then
  pass "id in frontmatter matches filename"
else
  fail "id mismatch: file=$FILE_ID, filename=$ID"
fi

# ---------------------------------------------------------------------------
# 2. Fill generated file with valid v2 content
# ---------------------------------------------------------------------------
echo "=== 2. Fill generated file with valid v2 content ==="
sed "s/__ID__/$ID/g" > "$TARGET" <<'TASKSPEC'
---
id: __ID__
title: Dummy self-test task
status: ready
format_version: 2
effort: S
budget_iterations: 15
agent: any
depends_on: []
touches_paths:
  - tasks/dummy.txt
source_note: self-test
created: 2026-05-27T00:00:00Z
tags: []
---

# Dummy self-test task

> **Why:** This is a dummy task for self-testing the task-spec skill.

---

## Goal

Verify the task-spec skill toolchain works end-to-end.

---

## Context

Minimal context for testing.

---

## Success Criteria

```bash
# eval-1: dummy passes
eval_1() {
  echo "PASS: dummy eval 1"
}

# eval-2: dummy passes
eval_2() {
  echo "PASS: dummy eval 2"
}

# eval-3: dummy passes
eval_3() {
  echo "PASS: dummy eval 3"
}
```

---

## Validation Card

```yaml
success_criteria:
  - id: eval_1
    description: dummy passes
    runnable: bash
    terminal: true
    expected_duration_sec: 10
  - id: eval_2
    description: dummy passes
    runnable: bash
    terminal: true
    expected_duration_sec: 10
  - id: eval_3
    description: dummy passes
    runnable: bash
    terminal: true
    expected_duration_sec: 10

retry_policy:
  max_iterations: 15
  circuit_breaker_no_progress: 3
  on_terminal_failure: park_with_context

agent_contract:
  version: 2
  read: [intent, contract, guardrails, operations]
  produce:
    - tests
  required_tools: [git, bash]
  timeout_minutes: 30
  sandbox_type: host
  output_artifacts: []
  mcp_dependencies: []
  emit:
    - pass
    - fail
    - retry_with_reason
    - parked_with_context
  backend_metadata: {}
```

---

## Exit Check

```bash
eval_1 && eval_2 && eval_3
```

---

## Rollback Plan

(none — this task is append-only)

---

## Observability Hooks

(none — no runtime observability required)

---

## Anti-Patterns

- Don't skip cleanup — tests must clean up after themselves.

---

## Do-Not-Touch

(none)

---

## Open Questions

(none — this task is fully specified)
TASKSPEC

pass "wrote valid v2 task spec"

# ---------------------------------------------------------------------------
# 3. validate-task-spec.sh — expect PASS
# ---------------------------------------------------------------------------
echo "=== 3. validate-task-spec.sh (expect PASS) ==="
val_out=$(bash "$SCRIPT_DIR/validate-task-spec.sh" "$TARGET" 2>&1) && val_rc=0 || val_rc=$?
if [[ $val_rc -eq 0 ]] && echo "$val_out" | grep -q "OK:"; then
  pass "validator passes on valid task"
else
  fail "validator did not pass on valid task (rc=$val_rc, out=$val_out)"
fi

# ---------------------------------------------------------------------------
# 4. Controlled error — expect FAIL
# ---------------------------------------------------------------------------
echo "=== 4. validate-task-spec.sh with controlled error (expect FAIL) ==="
echo "{{TODO: this should fail}}" >> "$TARGET"
val_out=$(bash "$SCRIPT_DIR/validate-task-spec.sh" "$TARGET" 2>&1) && val_rc=0 || val_rc=$?
if [[ $val_rc -ne 0 ]] && echo "$val_out" | grep -qi "placeholder"; then
  pass "validator catches placeholder regression"
else
  fail "validator did not catch placeholder (rc=$val_rc, out=$val_out)"
fi
# Restore valid file (portable sed — no -i flag)
sed '/{{TODO: this should fail}}/d' "$TARGET" > "${TARGET}.tmp" && mv "${TARGET}.tmp" "$TARGET"

# ---------------------------------------------------------------------------
# 5. transition-status.sh — ready → in-progress
# ---------------------------------------------------------------------------
echo "=== 5. transition-status.sh: ready → in-progress ==="
bash "$SCRIPT_DIR/transition-status.sh" "$ID" in-progress >/dev/null 2>&1 && trans_rc=0 || trans_rc=$?
if [[ $trans_rc -eq 0 ]]; then
  pass "transition without an optional reason succeeds"
else
  fail "transition without an optional reason failed (rc=$trans_rc)"
fi

if grep -q "^status: in-progress" "$TARGET"; then
  pass "status updated to in-progress"
else
  fail "status not updated to in-progress"
fi

if [[ -f "tasks/${ID}.md" ]]; then
  pass "file remains in tasks/ for active status"
else
  fail "file missing from tasks/ after transition to in-progress"
fi

# ---------------------------------------------------------------------------
# 6. transition-status.sh — in-progress → done
# ---------------------------------------------------------------------------
echo "=== 6. transition-status.sh: in-progress → done ==="
# Completion is now a settled state, not a file move. Supply the acceptance
# envelope and passing receipt that the transition gate requires.
if bash "$SCRIPT_DIR/transition-status.sh" "$ID" done "premature" >/dev/null 2>&1; then
  fail "transition allowed done before acceptance and a passing receipt"
else
  pass "transition rejects premature done"
fi
if [[ -f "$TARGET" ]] && grep -q '^status: in-progress$' "$TARGET"; then
  pass "rejected done transition leaves the task unchanged"
else
  fail "rejected done transition mutated or moved the task"
fi
awk '
  /^tags:/ && !added {
    print
    print "signed_off: true"
    print "signed_off_by: self-test"
    print "signed_off_at: 2026-05-27T00:01:00Z"
    print "accepted: true"
    print "accepted_by: self-test"
    print "accepted_at: 2026-05-27T00:02:00Z"
    added=1
    next
  }
  { print }
' "$TARGET" > "${TARGET}.tmp" && mv "${TARGET}.tmp" "$TARGET"
mkdir -p cvg/receipts
printf '{"schema":"cvg.execution-receipt.v1","task_id":"%s","result":"pass"}\n' "$ID" \
  > "cvg/receipts/${ID}.json"
bash "$SCRIPT_DIR/transition-status.sh" "$ID" done "self-test" >/dev/null 2>&1 && trans_rc=0 || trans_rc=$?
if [[ $trans_rc -eq 0 ]]; then
  pass "transition to done succeeds"
else
  fail "transition to done failed (rc=$trans_rc)"
fi

if [[ -f "tasks/done/${ID}.md" ]]; then
  pass "file moved to tasks/done/"
else
  fail "file not moved to tasks/done/"
fi

if [[ ! -f "tasks/${ID}.md" ]]; then
  pass "file no longer in tasks/"
else
  fail "file still in tasks/ after done transition"
fi

# ---------------------------------------------------------------------------
# 7. rebuild-state.sh
# ---------------------------------------------------------------------------
echo "=== 7. rebuild-state.sh ==="
bash "$SCRIPT_DIR/rebuild-state.sh" >/dev/null 2>&1 && rebuild_rc=0 || rebuild_rc=$?
if [[ $rebuild_rc -eq 0 ]]; then
  pass "rebuild-state succeeds"
else
  fail "rebuild-state failed (rc=$rebuild_rc)"
fi

if [[ -f "tasks/_state.yaml" ]]; then
  pass "_state.yaml created"
else
  fail "_state.yaml not created"
fi

if grep -q "id: ${ID}" "tasks/_state.yaml"; then
  pass "_state.yaml contains test task"
else
  fail "_state.yaml missing test task"
fi

if grep -A5 "id: ${ID}" "tasks/_state.yaml" | grep -q "status: done"; then
  pass "_state.yaml reflects done status"
else
  fail "_state.yaml does not reflect done status"
fi

# ---------------------------------------------------------------------------
# 8. list-ready.sh
# ---------------------------------------------------------------------------
echo "=== 8. list-ready.sh ==="
list_out=$(bash "$SCRIPT_DIR/list-ready.sh" 2>&1 || true)
if ! echo "$list_out" | grep -q "$ID"; then
  pass "list-ready excludes done task"
else
  fail "list-ready incorrectly shows done task"
fi

# ---------------------------------------------------------------------------
# 9. archive.sh
# ---------------------------------------------------------------------------
echo "=== 9. archive.sh ==="
archive_out=$(bash "$SCRIPT_DIR/archive.sh" 2>&1 || true)
if echo "$archive_out" | grep -q "Archived: 0 done"; then
  pass "archive is no-op for already-archived task"
else
  fail "archive did not report 0 done moves"
fi

# ---------------------------------------------------------------------------
# 10. backup-backlog.sh
# ---------------------------------------------------------------------------
echo "=== 10. backup-backlog.sh ==="
bash "$SCRIPT_DIR/backup-backlog.sh" "$TMPDIR/backups" >/dev/null 2>&1 && backup_rc=0 || backup_rc=$?
if [[ $backup_rc -eq 0 ]]; then
  pass "backup-backlog succeeds"
else
  fail "backup-backlog failed (rc=$backup_rc)"
fi

found_backup=$(find "$TMPDIR/backups" -name "backlog-*.tar.gz" | head -1)
if [[ -n "$found_backup" ]]; then
  pass "backup archive created"
else
  fail "backup archive not created"
fi

echo "=== 11. safe-to-delegate.sh (pre-delegation gate) ==="
# $TARGET was moved to tasks/done/ in step 6, so generate a fresh fixture here.
# A valid (well-formed, unbuilt) spec should get VERDICT: DELEGATE (exit 0).
# A spec with a broken eval body should get DO NOT DELEGATE (exit non-zero).
gate_ok="tasks/T-20990910-gate-ok.md"
sed \
  -e 's/^id:.*/id: T-20990910-gate-ok/' \
  -e 's/^status:.*/status: ready/' \
  -e 's/^signed_off:.*/signed_off: false/' \
  -e 's/^signed_off_by:.*/signed_off_by: (none)/' \
  -e 's/^signed_off_at:.*/signed_off_at: (none)/' \
  -e 's/^accepted:.*/accepted: false/' \
  -e 's/^accepted_by:.*/accepted_by: (none)/' \
  -e 's/^accepted_at:.*/accepted_at: (none)/' \
  "tasks/done/${ID}.md" > "$gate_ok" 2>/dev/null \
  || sed 's/^id:.*/id: T-20990910-gate-ok/' "$TARGET" > "$gate_ok" 2>/dev/null

sd_out=$(bash "$SCRIPT_DIR/safe-to-delegate.sh" "$gate_ok" 2>&1) && sd_rc=0 || sd_rc=$?
if [[ $sd_rc -eq 0 ]] && echo "$sd_out" | grep -q "DELEGATE"; then
  pass "safe-to-delegate clears a valid spec"
else
  fail "safe-to-delegate blocked a valid spec (rc=$sd_rc)"
fi

gate_broken="tasks/T-20990911-gate-broken.md"
sed 's/eval_1() { true; }/eval_1() { if [ -z $x ; then return 1 fi }/' "$gate_ok" > "$gate_broken" 2>/dev/null
bash "$SCRIPT_DIR/safe-to-delegate.sh" "$gate_broken" >/dev/null 2>&1 && sdb_rc=0 || sdb_rc=$?
if [[ $sdb_rc -ne 0 ]]; then
  pass "safe-to-delegate blocks a broken-eval spec"
else
  fail "safe-to-delegate failed to block a broken-eval spec"
fi
rm -f "$gate_ok" "$gate_broken"

# ---------------------------------------------------------------------------
# `ready` is the frontier, not every green status field
# ---------------------------------------------------------------------------
# A spec whose depends_on is unmet is NOT dispatchable, however green its own
# status looks. This is the surface a Manager selects work from, so listing a
# blocked task there starts work whose inputs do not exist yet.
FRONT="$(mktemp -d -t cvg-front.XXXXXX)"
mkdir -p "$FRONT/tasks"
cat > "$FRONT/tasks/T-20990301-root.md" <<'EOF'
---
id: T-20990301-root
title: "root"
status: ready
effort: S
agent: any
depends_on: []
---
EOF
cat > "$FRONT/tasks/T-20990302-blocked.md" <<'EOF'
---
id: T-20990302-blocked
title: "blocked"
status: ready
effort: S
agent: any
depends_on: [T-20990301-root]
---
EOF
FRONT_OUT="$( (cd "$FRONT" && bash "$SCRIPT_DIR/list-ready.sh") 2>&1 || true )"
if echo "$FRONT_OUT" | grep -q 'T-20990301-root' && ! echo "$FRONT_OUT" | grep -q 'T-20990302-blocked'; then
  pass "ready shows the frontier and hides a blocked spec"
else
  fail "ready listed a spec whose depends_on is unmet"
fi
ALL_OUT="$( (cd "$FRONT" && bash "$SCRIPT_DIR/list-ready.sh" --all) 2>&1 || true )"
if echo "$ALL_OUT" | grep -q 'T-20990302-blocked'; then
  pass "--all still shows every status:ready spec"
else
  fail "--all did not restore the unfiltered listing"
fi
# A dangling depends_on must fail CLOSED, not silently unblock the task.
cat > "$FRONT/tasks/T-20990303-dangling.md" <<'EOF'
---
id: T-20990303-dangling
title: "dangling"
status: ready
effort: S
agent: any
depends_on: [T-19990101-nonexistent]
---
EOF
DANG_OUT="$( (cd "$FRONT" && bash "$SCRIPT_DIR/list-ready.sh") 2>&1 || true )"
if ! echo "$DANG_OUT" | grep -q 'T-20990303-dangling'; then
  pass "a dangling depends_on fails closed (task stays blocked)"
else
  fail "a task with a nonexistent dependency was listed as ready"
fi
rm -rf "$FRONT"

# ---------------------------------------------------------------------------
# Existence-only evals cannot be delegated blind
# ---------------------------------------------------------------------------
# `test -f x.py && grep -q assert x.py` is satisfied by `echo "# assert" > x.py`.
# An unsupervised loop would settle green on a stub, write a pass receipt, and
# report success having built nothing. The validator warns; the autonomy gate
# blocks; --supervised downgrades it, because then a human reads the diff.
STUBBABLE="tasks/T-20990201-stubbable.md"
cp "$FIXTURES_DIR/T-20260602-golden.md" "$STUBBABLE"
# the golden fixture declares README.md in touches_paths
[ -f README.md ] || printf '# readme\n' > README.md
python3 - "$STUBBABLE" <<'PYEOF'
import re, sys
p = sys.argv[1]
s = open(p).read()
s = re.sub(r'^id:.*$', 'id: T-20990201-stubbable', s, count=1, flags=re.M)
s = s.replace("! grep -q 'NEVERMATCH' README.md",
              "test -f README.md && grep -q 'readme' README.md")
open(p, 'w').write(s)
PYEOF

v_out="$(bash "$SCRIPT_DIR/validate-task-spec.sh" "$STUBBABLE" 2>&1 || true)"
if echo "$v_out" | grep -q 'existence-only evals'; then
  pass "the validator warns on existence-only evals"
else
  fail "existence-only evals passed the validator unnoticed"
fi

bash "$SCRIPT_DIR/safe-to-delegate.sh" "$STUBBABLE" >/dev/null 2>&1 && eo_rc=0 || eo_rc=$?
if [[ $eo_rc -ne 0 ]]; then
  pass "the autonomy gate BLOCKS a spec a stub would satisfy"
else
  fail "a stubbable spec was cleared for blind delegation"
fi

bash "$SCRIPT_DIR/safe-to-delegate.sh" --supervised "$STUBBABLE" >/dev/null 2>&1 && sup_rc=0 || sup_rc=$?
if [[ $sup_rc -eq 0 ]]; then
  pass "--supervised downgrades it (a human is reading the diff)"
else
  fail "--supervised did not relax the existence-only block"
fi

# An eval that RUNS something is not existence-only, even if it also stats a file.
REAL="tasks/T-20990202-real.md"
sed 's/^id:.*/id: T-20990202-real/' "$STUBBABLE" > "$REAL"
python3 - "$REAL" <<'PYEOF'
import sys
p = sys.argv[1]; s = open(p).read()
s = s.replace("test -f README.md && grep -q 'readme' README.md",
              "test -f README.md && python3 -c \"import sys; sys.exit(0)\"")
open(p, 'w').write(s)
PYEOF
real_out="$(bash "$SCRIPT_DIR/validate-task-spec.sh" "$REAL" 2>&1 || true)"
if ! echo "$real_out" | grep -q 'existence-only evals'; then
  pass "an eval that executes the artifact is not flagged"
else
  fail "false positive: an executing eval was called existence-only"
fi
rm -f "$STUBBABLE" "$REAL"

# ---------------------------------------------------------------------------
# The index belongs to the workspace, never to the git root
# ---------------------------------------------------------------------------
# A nested workspace (proving ground, monorepo package, sub-project) must not
# spill its task list into the parent repo's root. This leaked for months: the
# validator anchored `_state.yaml` at the git root while check-path-policy.py
# already treated it as a sibling of the spec.
NEST="$(mktemp -d -t cvg-nest.XXXXXX)"
git -C "$NEST" init --quiet
git -C "$NEST" config user.email nest@test.local
git -C "$NEST" config user.name "nest test"
mkdir -p "$NEST/deep/workspace/tasks"
NESTED_SPEC="$NEST/deep/workspace/tasks/T-20260602-golden.md"
cp "$FIXTURES_DIR/T-20260602-golden.md" "$NESTED_SPEC"
# the golden fixture declares README.md in touches_paths, which resolves
# against the git root — unlike the index, which is workspace-scoped
printf '# readme\n' > "$NEST/README.md"
bash "$SCRIPT_DIR/validate-task-spec.sh" "$NESTED_SPEC" >/dev/null 2>&1 || true
if [ ! -e "$NEST/tasks/_state.yaml" ] && [ -f "$NEST/deep/workspace/tasks/_state.yaml" ]; then
  pass "the task index lands in the workspace, not the git root"
else
  fail "the task index leaked to the git root (nested workspace spills upward)"
fi
if grep -q 'path: tasks/T-20260602-golden.md' "$NEST/deep/workspace/tasks/_state.yaml" 2>/dev/null; then
  pass "indexed paths are workspace-relative, not git-root-relative"
else
  fail "indexed paths are not workspace-relative"
fi
rm -f "$NEST/deep/workspace/tasks/_state.yaml"
bash "$SCRIPT_DIR/validate-task-spec.sh" --no-state "$NESTED_SPEC" >/dev/null 2>&1 || true
if [ ! -e "$NEST/deep/workspace/tasks/_state.yaml" ]; then
  pass "--no-state makes structural validation genuinely read-only"
else
  fail "--no-state still wrote the derived task index"
fi
rm -rf "$NEST"

# ---------------------------------------------------------------------------
# ONE board per backlog — a finished spec does not start a second one
# ---------------------------------------------------------------------------
# transition-status.sh moves a spec into a status bucket (done/, parked/,
# queue/) and rebuild-state.sh has always scanned those buckets recursively into
# ONE index at the backlog root. The validator instead wrote `_state.yaml` as a
# plain sibling of the spec, so validating anything already moved to done/ built
# a SHADOW board inside the bucket — holding that one task, while the real index
# beside it went stale and unnoticed. Found as an untracked
# `cvg/tasks/done/_state.yaml` carrying 1 of 9 tasks.
BUCKET="$(mktemp -d -t cvg-bucket.XXXXXX)"
git -C "$BUCKET" init --quiet
git -C "$BUCKET" config user.email bucket@test.local
git -C "$BUCKET" config user.name "bucket test"
mkdir -p "$BUCKET/tasks/done"
cp "$FIXTURES_DIR/T-20260602-golden.md" "$BUCKET/tasks/done/T-20260602-golden.md"
printf '# readme\n' > "$BUCKET/README.md"
bash "$SCRIPT_DIR/validate-task-spec.sh" "$BUCKET/tasks/done/T-20260602-golden.md" >/dev/null 2>&1 || true
if [ ! -e "$BUCKET/tasks/done/_state.yaml" ] && [ -f "$BUCKET/tasks/_state.yaml" ]; then
  pass "a spec in done/ indexes at the backlog root, not into a shadow board"
else
  fail "validating a done/ spec forked a second _state.yaml inside the bucket"
fi
# The bucket must survive in the path, or the index cannot find the file again.
if grep -q 'path: tasks/done/T-20260602-golden.md' "$BUCKET/tasks/_state.yaml" 2>/dev/null; then
  pass "…and the indexed path keeps the bucket (tasks/done/T-…)"
else
  fail "bucketed path lost or mis-anchored: $(grep '  path:' "$BUCKET/tasks/_state.yaml" 2>/dev/null | head -1 || true)"
fi
# THE ROW THAT MATTERS. Two writers now share one file, so they must agree on
# what paths are relative to — otherwise a validate after a rebuild silently
# mixes two path styles in the same list and every consumer has to guess.
( cd "$BUCKET" && bash "$SCRIPT_DIR/validate-task-spec.sh" tasks/done/T-20260602-golden.md ) >/dev/null 2>&1 || true
# `|| true` on every read: the suite runs under `set -e`, and a regression that
# stops writing this file would otherwise KILL the run on a failed grep instead
# of printing the red row that names the problem. A test that crashes tells you
# less than one that fails.
BUCKET_V="$(grep '  path:' "$BUCKET/tasks/_state.yaml" 2>/dev/null | sort -u || true)"
( cd "$BUCKET" && bash "$SCRIPT_DIR/rebuild-state.sh" ) >/dev/null 2>&1 || true
BUCKET_R="$(grep '  path:' "$BUCKET/tasks/_state.yaml" 2>/dev/null | sort -u || true)"
if [ -n "$BUCKET_V" ] && [ "$BUCKET_V" = "$BUCKET_R" ]; then
  pass "validate-task-spec and rebuild-state anchor paths identically"
else
  fail "the two index writers disagree (validate: ${BUCKET_V:-none} / rebuild: ${BUCKET_R:-none})"
fi

# A rebuild carries top-level queue/stats sections. Validating one task after
# that rebuild must replace its task record inside tasks:, never append a record
# below stats: (which creates a structurally misleading YAML document).
SECOND="$BUCKET/tasks/done/T-20260603-second.md"
sed 's/T-20260602-golden/T-20260603-second/g' \
  "$FIXTURES_DIR/T-20260602-golden.md" > "$SECOND"
( cd "$BUCKET" && bash "$SCRIPT_DIR/rebuild-state.sh" ) >/dev/null 2>&1 || true
( cd "$BUCKET" && bash "$SCRIPT_DIR/validate-task-spec.sh" \
    tasks/done/T-20260602-golden.md ) >/dev/null 2>&1 || true
STATE="$BUCKET/tasks/_state.yaml"
LAST_TASK_LINE="$(grep -n '^- id:' "$STATE" 2>/dev/null | tail -1 | cut -d: -f1 || true)"
STATS_LINE="$(grep -n '^stats:' "$STATE" 2>/dev/null | head -1 | cut -d: -f1 || true)"
TOP_SECTIONS="$(grep -Ec '^(tasks|ready_queue|in_progress|blocked|stats):$' "$STATE" 2>/dev/null || true)"
if [ -n "$LAST_TASK_LINE" ] && [ -n "$STATS_LINE" ] \
  && [ "$LAST_TASK_LINE" -lt "$STATS_LINE" ] \
  && [ "$TOP_SECTIONS" -eq 5 ] \
  && grep -q '^- id: T-20260602-golden$' "$STATE" \
  && grep -q '^- id: T-20260603-second$' "$STATE" \
  && grep -q '^  total: 2$' "$STATE"; then
  pass "validate after rebuild keeps every task inside one canonical YAML document"
else
  fail "validate after rebuild corrupted tasks/queues/stats structure"
fi
rm -rf "$BUCKET"

# ---------------------------------------------------------------------------
# The backlog's WRITE SURFACE is touches_paths + creates_paths
# ---------------------------------------------------------------------------
# The overlap check looked at touches_paths alone. Every greenfield task declares
# its writes in creates_paths, so on a backlog of nine such specs the check had
# nothing to inspect and exited 0 in silence — while the property it exists to
# protect (no two tasks write the same file) went unverified. That property is
# what makes a swimlane decomposition safe to dispatch in parallel.
LINTER="$SCRIPT_DIR/lint-backlog.sh"

# lint-backlog.sh needs bash 4 (associative arrays); ts_require_bash4 re-execs
# under one if it can find it and exits 3 if it cannot. On a stock-macOS host —
# bash 3.2 only, which is this repo's portability FLOOR — `cvg lint` therefore
# cannot run at all, and these three rows would fail for the host's bash rather
# than for the behaviour they test. That is exactly what happened on CI's
# macos-latest leg while passing here, because homebrew bash 5 sits first on this
# author's PATH.
#
# So: find a bash 4 anywhere standard and use it. Only when none exists do we
# skip, and then LOUDLY — a quiet skip is how a gate stops meaning anything, and
# the repo's own CI header makes that argument about secret-gated jobs.
LINT_BASH=""
for _lb_cand in bash /opt/homebrew/bin/bash /usr/local/bin/bash /bin/bash; do
  _lb_major="$("$_lb_cand" -c 'echo ${BASH_VERSINFO[0]}' 2>/dev/null || echo 0)"
  if [ "${_lb_major:-0}" -ge 4 ] 2>/dev/null; then LINT_BASH="$_lb_cand"; break; fi
done

if [ -z "$LINT_BASH" ]; then
  echo "  SKIP  backlog write-surface rows — no bash >= 4 on this host, so"
  echo "        \`cvg lint\` cannot run here at all (see ts_require_bash4)."
  echo "        This is a real gap in the product, not in the test: lint-backlog.sh"
  echo "        uses associative arrays against a stated bash 3.2 floor."
else

LB="$(mktemp -d -t ts-lintbacklog-XXXXXX)"
mkdir -p "$LB/tasks"
_mkspec() {  # _mkspec <name> <created-path>
  cat > "$LB/tasks/T-20260101-$1.md" <<EOF
---
id: T-20260101-$1
title: "lint probe $1"
status: ready
format_version: 3
effort: S
agent: any
depends_on: []
touches_paths: []
creates_paths:
  - $2
---
# lint probe $1
EOF
}

# Two tasks CREATING one path: both claim authorship, so whichever runs second
# clobbers the first or fails. That is an error, not a contention warning.
_mkspec collide-a cvg/capture/shared.py
_mkspec collide-b cvg/capture/shared.py
set +e
LB_OUT="$(TASKSPEC_BACKLOG_DIR="$LB/tasks" "$LINT_BASH" "$LINTER" 2>&1)"; LB_RC=$?
set -e
if [[ $LB_RC -ne 0 ]] && grep -q 'creates_paths collision' <<<"$LB_OUT"; then
  pass "a creates_paths collision is caught (it was invisible before)"
else
  fail "two tasks creating the same file linted clean (rc=$LB_RC)"
fi

# Disjoint surfaces must stay clean AND be reported as a concurrency partition,
# because that report is what tells a fleet which tasks may run side by side.
rm -f "$LB/tasks"/*.md
_mkspec lane-cap cvg/capture/orders.py
_mkspec lane-srv cvg/serve/api.py
_mkspec lane-tf  cvg/transform/silver.sql
set +e
LB_OUT2="$(TASKSPEC_BACKLOG_DIR="$LB/tasks" "$LINT_BASH" "$LINTER" 2>&1)"; LB_RC2=$?
set -e
if [[ $LB_RC2 -eq 0 ]] && grep -q 'concurrency partition' <<<"$LB_OUT2" \
  && grep -q 'cvg/capture' <<<"$LB_OUT2" && grep -q 'cvg/serve' <<<"$LB_OUT2" \
  && grep -q 'cvg/transform' <<<"$LB_OUT2"; then
  pass "write-disjoint lanes lint clean and report their concurrency partition"
else
  fail "the concurrency partition was not reported (rc=$LB_RC2)"
fi

# A task spanning two prefixes is the reason a by-lane parallel dispatch would
# conflict, so it must be named rather than silently folded into both groups.
cat > "$LB/tasks/T-20260101-spanner.md" <<'EOF'
---
id: T-20260101-spanner
title: "lint probe spanner"
status: ready
format_version: 3
effort: S
agent: any
depends_on: []
touches_paths: []
creates_paths:
  - cvg/capture/edge.py
  - cvg/serve/edge.py
---
# lint probe spanner
EOF
LB_OUT3="$(TASKSPEC_BACKLOG_DIR="$LB/tasks" "$LINT_BASH" "$LINTER" 2>&1 || true)"
if grep -q 'T-20260101-spanner writes across 2 prefixes' <<<"$LB_OUT3"; then
  pass "a task that breaks the lane partition is named"
else
  fail "a cross-prefix task was not flagged"
fi
rm -rf "$LB"

# Batch rendering must keep timestamps distinct from counters and must never
# interpret user text as a sed program or hand-built JSON.
BATCH_ROOT="$(mktemp -d -t cvg-batch.XXXXXX)"
mkdir -p "$BATCH_ROOT/tasks"
printf '%s\n' 'safe-render: Fix A & B | C "quoted"' > "$BATCH_ROOT/intents.txt"
if TASKSPEC_BACKLOG_DIR="$BATCH_ROOT/tasks" \
  bash "$SCRIPT_DIR/batch-generate.sh" \
    --intent-file "$BATCH_ROOT/intents.txt" --effort S \
    --source-note 'docs/A&B|C "quoted"' --skip-validation >/dev/null 2>&1; then
  BATCH_SPEC="$(find "$BATCH_ROOT/tasks" -maxdepth 1 -name 'T-*-safe-render.md' -print | head -1)"
  if python3 - "$BATCH_SPEC" "$BATCH_ROOT/tasks/_metrics.jsonl" <<'PY'
import datetime
import json
import pathlib
import sys

spec = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
title = next(line.removeprefix("title: ") for line in spec if line.startswith("title: "))
source = next(line.removeprefix("source_note: ") for line in spec if line.startswith("source_note: "))
created = next(line.removeprefix("created: ") for line in spec if line.startswith("created: "))
assert json.loads(title) == 'Fix A & B | C "quoted"'
assert json.loads(source) == 'docs/A&B|C "quoted"'
datetime.datetime.fromisoformat(created.replace("Z", "+00:00"))
events = [
    json.loads(line)
    for line in pathlib.Path(sys.argv[2]).read_text(encoding="utf-8").splitlines()
    if line
]
assert events[-1]["event"] == "created"
assert events[-1]["mode"] == "batch"
assert events[-1]["source"] == 'docs/A&B|C "quoted"'
PY
  then
    pass "batch generation preserves ISO timestamps and safely quotes template/JSON input"
  else
    fail "batch generation emitted malformed YAML scalars, timestamps, or JSONL"
  fi
else
  fail "batch generation failed on punctuation-safe user input"
fi
if TASKSPEC_BACKLOG_DIR="$BATCH_ROOT/tasks" \
  bash "$SCRIPT_DIR/batch-generate.sh" \
    --intent-file "$BATCH_ROOT/intents.txt" --effort S \
    --agent 'bad|agent' --skip-validation >/dev/null 2>&1; then
  fail "batch generation accepted an unsafe agent scalar"
else
  pass "batch generation rejects unsafe agent scalars"
fi
rm -rf "$BATCH_ROOT"
fi   # end: bash >= 4 available

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
printf "Results: %d passed, %d failed\n" "$PASS" "$FAIL"
echo "========================================"

if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
