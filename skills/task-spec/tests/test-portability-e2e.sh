#!/usr/bin/env bash
# test-portability-e2e.sh — End-to-end portability smoke test (WS8).
#
# Simulates a fresh-repo, fresh-author install + first-spec walkthrough in a
# disposable tempdir. Exits 0 only if every step from install through
# safe-to-delegate.sh --stamp produces the expected output.
#
# This is the contract for "scale anywhere by anyone": if this test exits 0,
# any new author at any repo can follow runbooks/first-spec-walkthrough.md
# and produce a signed_off:true spec on their first attempt.
#
# Usage:
#   bash tests/test-portability-e2e.sh

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0
FAIL=0

pass() {
  echo "  ✓ $1"
  PASS=$((PASS + 1))
}
fail() {
  echo "  ✗ $1" >&2
  FAIL=$((FAIL + 1))
}
note() {
  echo "  ⏭ $1"
}
skip_cross_engine() {
  if [[ "${TASK_SPEC_STRICT_CROSS_ENGINE:-0}" == "1" ]]; then
    fail "$1 (strict cross-engine proof is required)"
  else
    note "$1"
  fi
}

# Run a command with a wall-clock budget without relying on timeout(1)
# (absent on stock macOS). Returns the command's exit code, or 124 if it
# was killed for exceeding $1 seconds. Stdout/stderr pass through.
run_with_timeout() {
  local budget="$1"; shift
  "$@" &
  local cmd_pid=$!
  local waited=0
  while kill -0 "$cmd_pid" 2>/dev/null; do
    if [[ "$waited" -ge "$budget" ]]; then
      kill -TERM "$cmd_pid" 2>/dev/null || true
      sleep 1
      kill -KILL "$cmd_pid" 2>/dev/null || true
      wait "$cmd_pid" 2>/dev/null || true
      return 124
    fi
    sleep 1
    waited=$((waited + 1))
  done
  wait "$cmd_pid"
  return $?
}

# Project the load-bearing fields out of a consumer's JSON onto one canonical,
# comparable line. Reads JSON on stdin. This is the EQUIVALENCE oracle, so it
# compares structure, not just counts:
#   - eval_ids: the FULL ORDERED LIST (not len()). Two consumers that each find
#     3 evals but disagree on WHICH 3 must now diverge here — a count would have
#     hidden that.
#   - validation_card: a canonicalized (sorted-key) projection of the
#     load-bearing contract keys, so "they agree" means they extracted the SAME
#     contract, not merely the same scalars.
# signed_off_sig is intentionally NOT projected: both consumers ignore it
# identically, so the equivalence diff stays honest.
load_bearing_line() {
  python3 -c '
import sys, json
d = json.load(sys.stdin)
def norm(x):
    # Coerce whole-number floats to ints so a YAML-typing difference between the
    # two engines (e.g. 30.0 vs 30 for a retry timeout) is NOT a false divergence.
    if isinstance(x, float) and x.is_integer():
        return int(x)
    if isinstance(x, dict):
        return {k: norm(v) for k, v in x.items()}
    if isinstance(x, list):
        return [norm(v) for v in x]
    return x
card = d.get("validation_card") or {}
def pick(m, *keys):
    return {k: m.get(k) for k in keys if isinstance(m, dict) and k in m}
card_proj = {
    "agent_contract": pick(card.get("agent_contract") or {}, "read", "write", "verify", "report"),
    "retry_policy": card.get("retry_policy"),
    "success_criteria_keys": sorted((card.get("success_criteria") or {}).keys())
        if isinstance(card.get("success_criteria"), dict) else card.get("success_criteria"),
}
proj = {
    "id": d.get("id"),
    "status": d.get("status"),
    "execution_backend": d.get("execution_backend"),
    "signed_off": d.get("signed_off"),
    "eval_ids": d.get("eval_ids", []),
    "validation_card": card_proj,
}
print(json.dumps(norm(proj), sort_keys=True))
'
}

# Isolated tempdir
TMP=$(mktemp -d -t task-spec-e2e-XXXXXX)
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"
git init --quiet
git config user.email "test@e2e.local"
git config user.name "e2e test"

# macOS lacks flock(1); provide a minimal shim for isolated single-threaded tests
if ! command -v flock >/dev/null 2>&1; then
  mkdir -p "$TMP/bin"
  cat > "$TMP/bin/flock" <<'EOF'
#!/usr/bin/env bash
# Minimal flock shim for isolated test environments.
shift; shift; "$@"
EOF
  chmod +x "$TMP/bin/flock"
  export PATH="$TMP/bin:$PATH"
fi

echo "═══ Step 1: Install into fresh tempdir ═══"
if bash "$SKILL_DIR/scripts/install.sh" --target "$TMP" >/dev/null 2>&1; then
  pass "install.sh succeeded"
else
  fail "install.sh failed"
fi

INSTALLED="$TMP/.claude/skills/task-spec"
# CHANGELOG.md is deliberately absent: it is a PACKAGE artifact at the repo root,
# not part of a skill's install payload (promoted 2026-07-29).
for f in SKILL.md plugin.json marketplace.json scripts/_lib.sh; do
  if [[ -e "$INSTALLED/$f" ]]; then
    pass "installed: $f"
  else
    fail "missing: $f"
  fi
done

# Source the canonical version so these assertions never go stale on a bump.
EXPECTED_VERSION=$(grep -m1 '^TASKSPEC_VERSION=' "$INSTALLED/scripts/_lib.sh" | sed -E 's/^TASKSPEC_VERSION="?([^"]*)"?.*/\1/')

echo ""
echo "═══ Step 2: --version reports task-spec v$EXPECTED_VERSION ═══"
for s in install validate-task-spec safe-to-delegate generate-task-spec list-ready; do
  ver=$(bash "$INSTALLED/scripts/$s.sh" --version 2>&1)
  if [[ "$ver" == "task-spec v$EXPECTED_VERSION" ]]; then
    pass "$s.sh --version → $ver"
  else
    fail "$s.sh --version → '$ver' (expected 'task-spec v$EXPECTED_VERSION')"
  fi
done

echo ""
echo "═══ Step 3: GENERATE a spec ═══"
gen_out=$(bash "$INSTALLED/scripts/generate-task-spec.sh" e2e-health-endpoint S any "portability test" 2>&1)
if echo "$gen_out" | grep -q '^Spec written:'; then
  pass "generator wrote a spec"
else
  fail "generator output missing 'Spec written:' header"
fi
if echo "$gen_out" | grep -q "task_spec_version: $EXPECTED_VERSION"; then
  pass "generator stamped version $EXPECTED_VERSION"
else
  fail "generator did not stamp version $EXPECTED_VERSION"
fi
if echo "$gen_out" | grep -q 'Next: .*safe-to-delegate.sh --stamp'; then
  pass "generator printed --stamp breadcrumb"
else
  fail "generator missing --stamp breadcrumb"
fi

SPEC=$(find tasks -name 'T-*.md' | head -1)
if [[ -z "$SPEC" ]]; then
  fail "no spec file found in tasks/"
  echo ""
  echo "========================================"
  printf "Results: %d passed, %d failed\n" "$PASS" "$FAIL"
  echo "========================================"
  exit 1
fi
pass "spec file present at $SPEC"

echo ""
echo "═══ Step 4: Fill stubs (synthesize a minimal valid spec) ═══"
# Capture the generator-assigned id and ensure touches_paths references a real file
SPEC_ID=$(grep '^id:' "$SPEC" | awk '{print $2}')
echo "captured spec id: $SPEC_ID"
# Create a real target file the spec can reference
echo "# placeholder" > "$TMP/health-endpoint.md"
cat > "$SPEC" <<EOF
---
id: $SPEC_ID
title: E2E portability test spec
status: ready
format_version: 2
effort: S
budget_iterations: 15
agent: any
depends_on: []
touches_paths:
  - health-endpoint.md
source_note: portability-e2e
created: 2026-06-02T00:00:00Z
tags: [e2e]
owner: (none)
priority: P2
severity: cosmetic
due_date: (none)
precondition: (none)
blocked_reason: (none)
security_class: (none)
source_action_item: (none)
linear_ref: (none)
execution_backend: any
signed_off: false
signed_off_by: (none)
signed_off_at: (none)
---

# E2E portability test spec

> **Why:** Exercises install → generate → validate → safe-to-delegate end-to-end in a fresh tempdir.

## Goal
Prove the skill is portable.

## Context
This spec is synthesized by tests/test-portability-e2e.sh.

## Success Criteria
\`\`\`bash
eval_1() {
  ! grep -q 'NEVERMATCH-EVER' health-endpoint.md
}
\`\`\`

## Validation Card
\`\`\`yaml
success_criteria:
  - id: eval_1
    description: spec file does not contain literal NEVERMATCH-EVER
    runnable: bash
    check_type: deterministic
    terminal: true
    expected_duration_sec: 1
retry_policy:
  max_iterations: 15
  circuit_breaker_no_progress: 3
  on_terminal_failure: park_with_context
agent_contract:
  version: 2
  read: [intent, contract, guardrails, operations]
  produce:
    - code
  required_tools: [bash]
  timeout_minutes: 30
  sandbox_type: host
  output_artifacts: []
  mcp_dependencies: []
  emit:
    - pass
    - fail
  backend_metadata: {}
\`\`\`

## Exit Check
\`\`\`bash
eval_1
\`\`\`

## Rollback Plan
(none — e2e fixture)

## Observability Hooks
(none — e2e fixture)

## Anti-Patterns
- **Don't ship this spec** — it is a portability fixture.
- **Don't trust the eval** — it is intentionally trivial.
- **Don't bypass the gate** — the whole point is that the gate stamps.

## Do-Not-Touch
- src/

## Open Questions
(none — this is a fixture)
EOF

# Move the file into the backlog dir's expected name (the generator-named slug)
cd tasks
SPEC_NAME=$(basename "$SPEC")
cd "$TMP"

# Re-run validate to confirm
if bash "$INSTALLED/scripts/validate-task-spec.sh" "$SPEC" >/dev/null 2>&1; then
  pass "validate-task-spec.sh exits 0 on synthesized spec"
else
  fail "validate-task-spec.sh rejected the synthesized spec"
  bash "$INSTALLED/scripts/validate-task-spec.sh" "$SPEC" 2>&1 | head -5
fi

echo ""
echo "═══ Step 5: GATE (safe-to-delegate.sh --stamp) ═══"
gate_out=$(bash "$INSTALLED/scripts/safe-to-delegate.sh" --stamp --stamp-by "e2e-test" "$SPEC" 2>&1) || true
if echo "$gate_out" | grep -q "VERDICT: DELEGATE"; then
  pass "gate reported DELEGATE"
else
  fail "gate did not report DELEGATE"
  echo "$gate_out" | tail -10
fi
if echo "$gate_out" | grep -q "stamped signed_off: true"; then
  pass "gate stamped signed_off:true"
else
  fail "gate did not stamp signed_off:true"
fi

# Verify the spec now has signed_off:true with envelope
SIGNED=$(grep '^signed_off:' "$SPEC" | awk '{print $2}')
SIGNED_BY=$(grep '^signed_off_by:' "$SPEC" | awk '{print $2}')
SIGNED_AT=$(grep '^signed_off_at:' "$SPEC" | awk '{print $2}')
if [[ "$SIGNED" == "true" ]]; then
  pass "spec frontmatter signed_off: true"
else
  fail "spec frontmatter signed_off: $SIGNED (expected true)"
fi
if [[ "$SIGNED_BY" == "e2e-test" ]]; then
  pass "spec frontmatter signed_off_by: e2e-test"
else
  fail "spec frontmatter signed_off_by: $SIGNED_BY (expected e2e-test)"
fi
if [[ "$SIGNED_AT" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z?$ ]]; then
  pass "spec frontmatter signed_off_at is ISO-8601"
else
  fail "spec frontmatter signed_off_at: $SIGNED_AT (not ISO-8601)"
fi

# Re-validate the stamped spec to confirm structural sign-off envelope check accepts it
if bash "$INSTALLED/scripts/validate-task-spec.sh" "$SPEC" >/dev/null 2>&1; then
  pass "validate accepts the stamped spec (sign-off envelope OK)"
else
  fail "validate REJECTED the stamped spec — sign-off envelope check too strict?"
fi

echo ""
echo "═══ Step 6: Schema fidelity (Python consumer) ═══"
# Validate that the reference Python consumer can parse a v2.1 spec and exits 0.
# The installer copies references/schemas/ + references/examples/, so we point
# the consumer at the installed copy and run it against the canonical golden fixture.
GOLDEN_SRC="$SKILL_DIR/tests/fixtures/T-20260602-golden.md"
GOLDEN_DST="$TMP/T-20260602-golden.md"
if [[ -f "$GOLDEN_SRC" ]]; then
  cp "$GOLDEN_SRC" "$GOLDEN_DST"
  pass "copied golden fixture into tempdir"
else
  fail "missing golden fixture at $GOLDEN_SRC"
fi

PY_CONSUMER="$INSTALLED/references/examples/consume-task-spec.py"
if [[ -f "$PY_CONSUMER" ]]; then
  pass "python consumer present at references/examples/consume-task-spec.py"
else
  # Fall back to source copy if installer did not propagate references/.
  PY_CONSUMER="$SKILL_DIR/references/examples/consume-task-spec.py"
  if [[ -f "$PY_CONSUMER" ]]; then
    pass "python consumer present (source copy)"
  else
    fail "python consumer missing at both installed and source locations"
  fi
fi

PY_JSON=""
if [[ -f "$PY_CONSUMER" && -f "$GOLDEN_DST" ]]; then
  set +e
  PY_JSON=$(python3 "$PY_CONSUMER" "$GOLDEN_DST" 2>/dev/null)
  py_rc=$?
  set -e
  if [[ "$py_rc" -eq 0 ]]; then
    pass "python consumer parsed golden fixture (exit 0)"
  else
    fail "python consumer failed on golden fixture"
    python3 "$PY_CONSUMER" "$GOLDEN_DST" 2>&1 | head -10
  fi
fi

echo ""
echo "═══ Step 7: Cross-engine equivalence (Python vs TypeScript) ═══"
# B3: prove "any engine can consume" by demonstration, not assertion. Run the
# shipped TypeScript consumer on the SAME golden fixture the Python consumer
# parsed, then assert the load-bearing fields (id, status, execution_backend,
# signed_off, eval count) are EQUAL between the two engines. This is also the
# TS consumer's first CI coverage: a smoke test that the .ts compiles and runs.
#
# Floor preservation: local users without Node may skip this optional reference
# proof. CI sets TASK_SPEC_STRICT_CROSS_ENGINE=1, making every skip a failure.
TS_DIR="$INSTALLED/references/examples"
TS_CONSUMER="$TS_DIR/consume-task-spec.ts"
if [[ ! -f "$TS_CONSUMER" ]]; then
  TS_DIR="$SKILL_DIR/references/examples"
  TS_CONSUMER="$TS_DIR/consume-task-spec.ts"
fi

if ! command -v node >/dev/null 2>&1; then
  skip_cross_engine "cross-engine proof skipped: node not present (any-agent floor preserved)"
elif [[ ! -f "$TS_CONSUMER" ]]; then
  skip_cross_engine "cross-engine proof skipped: TS consumer not found at references/examples/"
elif [[ -z "$PY_JSON" ]]; then
  skip_cross_engine "cross-engine proof skipped: python consumer produced no JSON to compare against"
else
  pass "node present ($(node --version 2>/dev/null)) — attempting cross-engine proof"

  TS_DEPS_OK=true
  if [[ ! -d "$TS_DIR/node_modules/ts-node" || ! -d "$TS_DIR/node_modules/yaml" || ! -d "$TS_DIR/node_modules/ajv" ]]; then
    if command -v npm >/dev/null 2>&1; then
      if [[ -f "$TS_DIR/package-lock.json" ]]; then
        npm_install=(npm --prefix "$TS_DIR" ci --no-audit --no-fund --silent)
        echo "  installing locked TS consumer deps (npm ci, 120s budget)…"
      else
        npm_install=(npm --prefix "$TS_DIR" install --no-audit --no-fund --silent)
        echo "  installing TS consumer deps (npm install, 120s budget)…"
      fi
      set +e
      run_with_timeout 120 "${npm_install[@]}" >/dev/null 2>&1
      npm_rc=$?
      set -e
      if [[ "$npm_rc" -ne 0 ]]; then
        TS_DEPS_OK=false
        if [[ "$npm_rc" -eq 124 ]]; then
          skip_cross_engine "cross-engine proof skipped: npm dependency install exceeded 120s budget (no hang)"
        else
          skip_cross_engine "cross-engine proof skipped: npm dependency install failed (rc=$npm_rc)"
        fi
      fi
    else
      TS_DEPS_OK=false
      skip_cross_engine "cross-engine proof skipped: npm not available to install TS deps"
    fi
  fi

  if [[ "$TS_DEPS_OK" == "true" ]]; then
    # Resolve a ts-node entry point deterministically: prefer the locally
    # installed .bin shim, fall back to npx --no-install. Run with $TS_DIR as
    # cwd so Node's node_modules resolution is unambiguous regardless of where
    # the test was invoked from.
    TS_BIN="$TS_DIR/node_modules/.bin/ts-node"
    run_ts_consumer() {
      if [[ -x "$TS_BIN" ]]; then
        ( cd "$TS_DIR" && "$TS_BIN" "$TS_CONSUMER" "$GOLDEN_DST" )
      else
        ( cd "$TS_DIR" && npx --no-install ts-node "$TS_CONSUMER" "$GOLDEN_DST" )
      fi
    }
    set +e
    TS_JSON=$(run_with_timeout 90 run_ts_consumer 2>/dev/null)
    ts_rc=$?
    set -e
    if [[ "$ts_rc" -eq 0 && -n "$TS_JSON" ]]; then
      pass "typescript consumer parsed golden fixture (exit 0)"

      set +e
      PY_LB=$(printf '%s' "$PY_JSON" | load_bearing_line)
      TS_LB=$(printf '%s' "$TS_JSON" | load_bearing_line)
      set -e

      if [[ -n "$PY_LB" && "$PY_LB" == "$TS_LB" ]]; then
        pass "cross-engine equivalence: id/status/execution_backend/signed_off + ordered eval_ids + canonicalized validation_card ALL EQUAL"
        echo "      both engines: $PY_LB"
      else
        fail "cross-engine load-bearing fields DIFFER between Python and TypeScript"
        echo "      python: $PY_LB" >&2
        echo "      ts:     $TS_LB" >&2
      fi
    elif [[ "$ts_rc" -eq 124 ]]; then
      skip_cross_engine "cross-engine proof skipped: TS consumer exceeded 90s budget (no hang)"
    else
      fail "typescript consumer failed on golden fixture (rc=$ts_rc) — .ts may have rotted"
      run_ts_consumer 2>&1 | head -10
    fi
  fi
fi

echo ""
echo "========================================"
printf "Results: %d passed, %d failed\n" "$PASS" "$FAIL"
echo "========================================"

if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
exit 0
