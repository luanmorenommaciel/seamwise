#!/bin/bash
# test-effort-sizing.sh — the six-tier effort gate (v3.4, tasks-all-the-way-down).
# Proves, discriminating:
#   · each LEAF tier (XS/S/M/L) validates within its write-surface budget
#   · a mis-sized leaf still validates but WARNS (budgets expose coarse decomposition)
#   · L requires execution_backend: glm
#   · an XL/XXL NODE without enough children FAILS (must decompose — no SDD escape)
#   · an XL/XXL NODE with children validates as a composition unit
#   · an unknown size FAILS
# The size dimension is isolated: every fixture is otherwise a valid profile: lite spec.
# bash 3.2-safe. Uses --skip-touches-paths so synthetic paths need not exist on disk.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
VAL="$HERE/../scripts/validate-task-spec.sh"
TOTAL=0; FAILED=0
pass() { printf 'ok    %-22s (exit %s)\n' "$1" "$2"; }
fail() { printf 'FAIL  %-22s %s\n' "$1" "$2"; FAILED=$((FAILED + 1)); }

# mkspec <file> <effort> <touches-csv> <creates-csv> <children-csv> <backend>
mkspec() {
  local f="$1" eff="$2" tou="$3" cre="$4" chi="$5" be="${6:-any}" slug p c
  slug="$(printf '%s' "$eff" | tr '[:upper:]' '[:lower:]' | tr -cd '[:lower:]')"; [ -n "$slug" ] || slug="x"
  {
    printf -- '---\n'
    printf 'id: T-20260721-size-%s\n' "$slug"
    printf 'title: sizing fixture %s\n' "$eff"
    printf 'status: ready\nformat_version: 3\nprofile: lite\n'
    printf 'effort: %s\nbudget_iterations: 8\nagent: any\ndepends_on: []\n' "$eff"
    printf 'execution_backend: %s\n' "$be"
    printf 'touches_paths:\n'
    if [ -n "$tou" ]; then IFS=','; for p in $tou; do printf -- '  - %s\n' "$p"; done; unset IFS
    else printf -- '  - README.md\n'; fi
    if [ -n "$cre" ]; then printf 'creates_paths:\n'; IFS=','; for p in $cre; do printf -- '  - %s\n' "$p"; done; unset IFS; fi
    if [ -n "$chi" ]; then printf 'children:\n'; IFS=','; for c in $chi; do printf -- '  - %s\n' "$c"; done; unset IFS; fi
    printf 'source_note: sizing test\ncreated: 2026-07-21T00:00:00Z\n'
    printf -- '---\n'
    cat <<'BODY'

# sizing fixture

## Goal
Prove the effort-gate tier behaves.

## Success Criteria
```bash
eval_1() { true; }
```

## Validation Card
```yaml
success_criteria:
  - id: eval_1
    description: synthetic
    runnable: bash
    check_type: deterministic
    terminal: true
    expected_duration_sec: 1
retry_policy:
  max_iterations: 8
  circuit_breaker_no_progress: 3
  on_terminal_failure: park_with_context
agent_contract:
  version: 2
  read: [intent]
  produce: [code]
  required_tools: [bash]
  timeout_minutes: 10
  sandbox_type: host
  output_artifacts: []
  mcp_dependencies: []
  emit: [pass, fail]
  backend_metadata: {}
```

## Exit Check
```bash
eval_1
```
BODY
  } > "$f"
}

# run <name> <want_exit> <grep> <effort> <touches> <creates> <children> <backend>
run() {
  TOTAL=$((TOTAL + 1))
  local name="$1" we="$2" g="$3"; shift 3
  local eff="$1" slug d f out rc
  slug="$(printf '%s' "$eff" | tr '[:upper:]' '[:lower:]' | tr -cd '[:lower:]')"; [ -n "$slug" ] || slug="x"
  d="$(mktemp -d)"; f="$d/T-20260721-size-$slug.md"   # id must match filename basename
  mkspec "$f" "$@"
  out="$(bash "$VAL" --skip-touches-paths "$f" 2>&1)"; rc=$?
  rm -rf "$d"
  if [ "$rc" -ne "$we" ]; then fail "$name" "exit $rc want $we"; printf '%s\n' "$out" | tail -3 | sed 's/^/      | /'; return; fi
  if [ -n "$g" ] && ! printf '%s\n' "$out" | grep -qiE "$g"; then fail "$name" "missing /$g/"; printf '%s\n' "$out" | tail -3 | sed 's/^/      | /'; return; fi
  pass "$name" "$rc"
}

echo "== effort-gate v3.4 · six-tier sizing =="
# leaves within budget → valid
run "XS leaf ok"        0 ''                          XS  "README.md"          "" "" any
run "S leaf ok"         0 ''                          S   "a1,a2"              "" "" any
run "M leaf ok"         0 ''                          M   "a1,a2,a3"           "" "" any
run "L leaf glm ok"     0 ''                          L   "a1,a2,a3,a4,a5"     "" "" glm
# The L gate is about LONG-HORIZON capability, not one vendor: execution_backend
# is an open string, so the eligible set is configurable (TS_LONG_HORIZON_BACKENDS).
run "L leaf claude ok"  0 ''                          L   "a1,a2,a3,a4,a5"     "" "" claude
run "L leaf codex ok"   0 ''                          L   "a1,a2,a3,a4,a5"     "" "" codex
run "L leaf kimi ok"    0 ''                          L   "a1,a2,a3,a4,a5"     "" "" kimi
# L guardrail
run "L needs long-horizon" 1 'requires a LONG-HORIZON builder' L "a1"          "" "" any
# mis-sized leaf → valid but WARNS (budget breach = coarse decomposition)
run "S mis-sized warns" 0 'Mis-sized'                 S   "a1,a2,a3,a4,a5"     "" "" any
# NODES must decompose — no SDD escape
run "XL no children"    1 'MUST declare children'     XL  "a1"                 "" ""          any
run "XXL too few kids"  1 'MUST declare children'     XXL "a1"                 "" "T-1,T-2"   any
# NODES with children → valid composition units
run "XL with children"  0 'composition unit'          XL  "a1"                 "" "T-a,T-b"       any
run "XXL with children" 0 'composition unit'          XXL "a1"                 "" "T-a,T-b,T-c"   any
# unknown size
run "bad size fails"    1 'effort must be one of'     ZZ  "a1"                 "" "" any

echo
if [ "$FAILED" -eq 0 ]; then echo "PASS — all $TOTAL rows green."; exit 0
else echo "FAIL — $FAILED of $TOTAL rows red." >&2; exit 1; fi
