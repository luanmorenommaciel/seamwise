#!/usr/bin/env bash
# test-bash-portability.sh — Guard against bash-4-only constructs leaking into
# the core gate path, and confirm the aux scripts gate themselves.
#
# Asserts:
#   (a) `bash -n` (syntax check) passes for every .sh under scripts/ using the
#       bash this test runs under.
#   (b) The four core-path scripts (validate-task-spec.sh, safe-to-delegate.sh,
#       run-task-spec.sh, _lib.sh) contain NO `declare -A` and NO mapfile.
#       (These must stay runnable on macOS system bash 3.2.57.)
#   (c) lint-backlog.sh and query-metrics.sh both call ts_require_bash4, the
#       bash-4 self-detecting guard.
#
# Prints a "Results: N passed, M failed" line. Exits non-zero if any fail.

set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts" && pwd)"
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

# ---------------------------------------------------------------------------
# (a) bash -n syntax check for every .sh under scripts/
# ---------------------------------------------------------------------------
echo "=== (a) bash -n syntax check for every scripts/*.sh ==="
shopt -s nullglob
for sh in "$SCRIPTS_DIR"/*.sh; do
  name="$(basename "$sh")"
  if bash -n "$sh" 2>/dev/null; then
    pass "syntax ok: $name"
  else
    fail "syntax error: $name"
  fi
done
shopt -u nullglob

# ---------------------------------------------------------------------------
# (b) Core-path scripts must be bash-3.2-clean (no declare -A, no mapfile)
# Strip full-line comments before grepping so prose that *mentions* these
# constructs (e.g. _lib.sh documenting why the guard exists) does not trip the
# assertion — only executable usage breaks bash 3.2.
# ---------------------------------------------------------------------------
echo "=== (b) core-path scripts contain no bash-4-only constructs ==="
CORE_SCRIPTS=(validate-task-spec.sh safe-to-delegate.sh run-task-spec.sh _lib.sh)
for name in "${CORE_SCRIPTS[@]}"; do
  path="$SCRIPTS_DIR/$name"
  if [[ ! -f "$path" ]]; then
    fail "core script missing: $name"
    continue
  fi
  code="$(grep -vE '^[[:space:]]*#' "$path")"
  if echo "$code" | grep -Eq 'declare[[:space:]]+-A'; then
    fail "$name contains 'declare -A' (breaks bash 3.2)"
  else
    pass "$name has no 'declare -A'"
  fi
  if echo "$code" | grep -Eq '\b(mapfile|readarray)\b'; then
    fail "$name contains mapfile/readarray (breaks bash 3.2)"
  else
    pass "$name has no mapfile/readarray"
  fi
done

# ---------------------------------------------------------------------------
# (c) Aux scripts must call ts_require_bash4
# ---------------------------------------------------------------------------
echo "=== (c) aux scripts call ts_require_bash4 ==="
AUX_SCRIPTS=(lint-backlog.sh query-metrics.sh)
for name in "${AUX_SCRIPTS[@]}"; do
  path="$SCRIPTS_DIR/$name"
  if [[ ! -f "$path" ]]; then
    fail "aux script missing: $name"
    continue
  fi
  if grep -q 'ts_require_bash4' "$path"; then
    pass "$name calls ts_require_bash4"
  else
    fail "$name does NOT call ts_require_bash4 (would hard-fail on bash 3.2)"
  fi
done

# ---------------------------------------------------------------------------
# (d) Vendor-facing conformance runner + adapters must be bash-3.2-clean.
# These are NOT under scripts/ but a vendor on macOS system bash (3.2.57) must
# be able to run the conformance suite. A bash-4-only construct here silently
# no-ops the gate (mapfile leaves the fixture array empty), so guard it. Strip
# full-line comments first so prose mentioning the constructs is not flagged.
# ---------------------------------------------------------------------------
echo "=== (d) conformance runner + adapters are bash-3.2-clean ==="
CONF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/conformance" && pwd)"
shopt -s nullglob
CONF_SCRIPTS=("$CONF_DIR/run_conformance.sh" "$CONF_DIR"/adapters/*.sh)
shopt -u nullglob
for path in "${CONF_SCRIPTS[@]}"; do
  name="conformance/${path#"$CONF_DIR"/}"
  if [[ ! -f "$path" ]]; then
    fail "conformance script missing: $name"
    continue
  fi
  if bash -n "$path" 2>/dev/null; then
    pass "syntax ok: $name"
  else
    fail "syntax error: $name"
  fi
  code="$(grep -vE '^[[:space:]]*#' "$path")"
  if echo "$code" | grep -Eq '\b(mapfile|readarray)\b' || echo "$code" | grep -Eq 'declare[[:space:]]+-A'; then
    fail "$name contains a bash-4-only construct (mapfile/readarray/declare -A) — silently no-ops on bash 3.2"
  else
    pass "$name has no bash-4-only constructs"
  fi
done

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
