#!/usr/bin/env bash
# test-extractor-fuzz.sh — adversarial fuzz of the extract-and-run path (run-task-spec.sh).
#
# The heredoc-aware awk extractor in run-task-spec.sh is the most structurally
# complex parser in the skill, and the path prior review rounds under-tested.
# This suite throws adversarial spec structures at it and asserts two contracts:
#
#   (A) EXTRACTION CORRECTNESS — structures the extractor explicitly claims to
#       handle (arithmetic `<<`, heredoc delimiter literally "bash", tab-indented
#       `<<-`, fake fences/headers inside heredocs, nested heredocs, quoted
#       delimiters) must yield a runnable eval, not a truncated/parse-fail.
#
#   (B) ROBUSTNESS INVARIANT — in --ci mode the runner must ALWAYS emit parseable
#       JSON (a status line or a _runner parse-fail line) and NEVER leak a raw
#       bash/awk/sed error or hang, no matter how malformed the input. A machine
#       reading the runner's stdout depends on this.
#
# Each case runs in an isolated git tempdir. Portable timeout (no coreutils dep).
#
# Usage:
#   bash tests/test-extractor-fuzz.sh
#   bash tests/test-extractor-fuzz.sh --version

set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../scripts/_lib.sh
source "$SKILL_DIR/scripts/_lib.sh"
ts_version_flag "$@"

# SC2016: the fuzz cases below are LITERAL bash source (with $(( )), backticks,
# heredocs) that must reach the extractor un-expanded — single quotes are
# correct here, not a mistake. Disabled file-wide for that reason.
# shellcheck disable=SC2016

RUN="$SKILL_DIR/scripts/run-task-spec.sh"

PASS=0
FAIL=0
pass() { echo "  ✓ $1"; PASS=$((PASS + 1)); }
fail() { echo "  ✗ $1" >&2; FAIL=$((FAIL + 1)); }

# Portable timeout: run a command, kill it after N seconds. Echoes nothing;
# returns 137 if it had to be killed, else the command's exit code.
run_to() {
  local t="$1"; shift
  "$@" &
  local p=$!
  ( sleep "$t"; kill -9 "$p" 2>/dev/null ) &
  local w=$!
  wait "$p" 2>/dev/null
  local rc=$?
  kill "$w" 2>/dev/null
  return $rc
}

# Build a complete, valid-shaped spec with a custom Success Criteria + Exit Check.
wrap_spec() {
  local sc="$1" ec="$2"
  printf -- '---\nid: T-fuzz\nstatus: ready\nformat_version: 2\neffort: S\nagent: any\ntouches_paths: [README.md]\nsource_note: fuzz\nexecution_backend: any\nsigned_off: false\n---\n\n# Fuzz\n\n> **Why:** fuzz\n\n## Goal\nfuzz\n\n## Success Criteria\n'
  printf '```bash\n%s\n```\n' "$sc"
  printf '\n## Validation Card\n```yaml\nsuccess_criteria:\n  - id: eval_1\n    description: f\n    runnable: bash\n    check_type: deterministic\n    terminal: true\n    expected_duration_sec: 1\nretry_policy:\n  max_iterations: 15\n  circuit_breaker_no_progress: 3\n  on_terminal_failure: park_with_context\nagent_contract:\n  version: 2\n  read: [intent]\n  produce: [code]\n  required_tools: [bash]\n  timeout_minutes: 30\n  sandbox_type: host\n  output_artifacts: []\n  mcp_dependencies: []\n  emit: [pass, fail]\n```\n'
  printf '\n## Exit Check\n```bash\n%s\n```\n' "$ec"
  printf '\n## Rollback Plan\n(none)\n## Observability Hooks\n(none)\n## Anti-Patterns\n- none\n## Do-Not-Touch\n- none\n## Open Questions\n(none)\n'
}

WORK=$(mktemp -d -t ts-fuzz-XXXXXX)
(
  cd "$WORK" || exit 1
  git init --quiet
  git config user.email "fuzz@test.local"
  git config user.name "fuzz"
  echo "x" > README.md
) >/dev/null 2>&1

# behavior of the runner on the current spec.md: EXTRACTED|PARSEFAIL|LEAK|HANG
run_behavior() {
  local out rc bad
  out=$(cd "$WORK" && run_to 12 bash "$RUN" --ci spec.md 2>&1)
  rc=$?
  if [[ $rc -eq 137 ]]; then echo "HANG"; return; fi
  bad=$(printf '%s\n' "$out" | grep -vE '^\{|^$' | grep -iE 'syntax error|unbound|unexpected|: line [0-9]|awk:|sed:' | head -1)
  if [[ -n "$bad" ]]; then echo "LEAK:$bad"; return; fi
  if printf '%s\n' "$out" | grep -q '"eval":"_runner"'; then echo "PARSEFAIL"; return; fi
  if printf '%s\n' "$out" | grep -qE '"status":"(pass|fail)"'; then echo "EXTRACTED"; return; fi
  echo "UNKNOWN"
}

echo "═══ test-extractor-fuzz.sh (adversarial extract-and-run, v$TASKSPEC_VERSION) ═══"

# --- (A) extraction-correctness cases: must EXTRACT a runnable eval ---
echo "── (A) extraction correctness ──"
declare -a A_NAMES A_SC
add_a() { A_NAMES+=("$1"); A_SC+=("$2"); }
add_a "arith-shift"        'eval_1(){ x=$((1 << 2)); [ "$x" = 4 ]; }'
add_a "heredoc-EOF-bash"   'eval_1(){ cat >/dev/null <<bash
hi
bash
true; }'
add_a "heredoc-fake-fence" 'eval_1(){ cat >/dev/null <<EOF
```
EOF
true; }'
add_a "heredoc-fake-header" 'eval_1(){ cat >/dev/null <<EOF
## Exit Check
EOF
true; }'
add_a "nested-heredoc"     'eval_1(){ cat >/dev/null <<A
o
A
cat >/dev/null <<B
i
B
true; }'
add_a "heredoc-dquote"     'eval_1(){ cat >/dev/null <<"EOF"
x
EOF
true; }'
for i in "${!A_NAMES[@]}"; do
  wrap_spec "${A_SC[$i]}" 'eval_1' > "$WORK/spec.md"
  b=$(run_behavior)
  if [[ "$b" == "EXTRACTED" ]]; then pass "A:${A_NAMES[$i]} extracted"; else fail "A:${A_NAMES[$i]} -> $b (want EXTRACTED)"; fi
done

# --- (B) robustness invariant: NEVER hang, NEVER leak a raw error ---
echo "── (B) robustness invariant (no hang, no raw-error leak) ──"
declare -a B_NAMES B_SC
add_b() { B_NAMES+=("$1"); B_SC+=("$2"); }
add_b "emoji-body"        'eval_1(){ echo "😀𝕏 ünïçödé"; true; }'
add_b "two-evals"         'eval_1(){ true; }
eval_2(){ true; }'
add_b "unbalanced-brace"  'eval_1(){ true;'
add_b "fence-in-string"   'eval_1(){ s="```"; true; }'
add_b "header-looking-cmd" 'eval_1(){ echo "## not a header"; true; }'
add_b "backtick-cmd"      'eval_1(){ x=`echo hi`; true; }'
add_b "comment-only"      'eval_1(){ # c
true; }'
add_b "exit-in-eval"      'eval_1(){ (exit 0); }'
add_b "reads-stdin"       'eval_1(){ read -r line; [ -n "$line" ]; }'
add_b "many-heredocs"     'eval_1(){ for i in 1 2 3; do cat >/dev/null <<E
$i
E
done; true; }'
for i in "${!B_NAMES[@]}"; do
  wrap_spec "${B_SC[$i]}" 'eval_1' > "$WORK/spec.md"
  b=$(run_behavior)
  case "$b" in
    HANG|LEAK:*|UNKNOWN) fail "B:${B_NAMES[$i]} -> $b" ;;
    *) pass "B:${B_NAMES[$i]} clean ($b)" ;;
  esac
done

# --- (C) defense-in-depth on the EXIT CHECK runner ---
# The Exit Check produces the final verdict via its own `bash "$ec_script"`
# invocation, distinct from the per-eval runner, and also carries the
# < /dev/null guard. Note: a malformed Exit Check body fails at script-build /
# syntax time (bash reading a FILE does not block on stdin the way the per-eval
# `bash -c <string>` path can), so these cases are defense-in-depth coverage of
# the guarded path, NOT a proof the guard is load-bearing here. The load-bearing
# proof lives in case B:reads-stdin, which provably HANGS without the per-eval
# guard.
echo "── (C) exit-check robustness (defense-in-depth, no hang on malformed Exit Check) ──"
declare -a C_NAMES C_EC
add_c() { C_NAMES+=("$1"); C_EC+=("$2"); }
add_c "ec-unbalanced-quote" 'eval_1(){ echo "unterminated'
add_c "ec-unbalanced-btick" 'eval_1(){ echo `cat'
add_c "ec-heredoc-no-close" 'eval_1(){ cat <<EOF
never closed'
for i in "${!C_NAMES[@]}"; do
  wrap_spec 'eval_1(){ true; }' "${C_EC[$i]}" > "$WORK/spec.md"
  b=$(run_behavior)
  case "$b" in
    HANG) fail "C:${C_NAMES[$i]} -> HANG (exit-check runner blocked on stdin)" ;;
    LEAK:*|UNKNOWN) fail "C:${C_NAMES[$i]} -> $b" ;;
    *) pass "C:${C_NAMES[$i]} clean ($b)" ;;
  esac
done

rm -rf "$WORK"

echo ""
echo "========================================"
printf "Results: %d passed, %d failed\n" "$PASS" "$FAIL"
echo "========================================"
[[ $FAIL -gt 0 ]] && exit 1
exit 0
