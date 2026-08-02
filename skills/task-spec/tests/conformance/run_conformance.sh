#!/usr/bin/env bash
# run_conformance.sh — REFERENCE conformance driver for the Task-Spec agent contract.
#
# This is ONE canonical reference harness. Vendors are still expected to write
# their own (see README.md "How to vendor these fixtures") — this driver shows
# the contract a conformant harness must satisfy and gives the skill a way to
# self-certify its own reference execution path.
#
# Design:
#   - Black-box engine-adapter indirection. The driver SHELLS OUT to an adapter
#     and never imports engine internals. Pick the adapter via:
#       TASKSPEC_ENGINE_CMD env var   (highest precedence)
#       --adapter PATH                (CLI override)
#       default: adapters/self.sh     (the skill's own reference path)
#   - SELF-TEST FLOOR first: every T-conformance-*.md fixture must itself pass
#     validate-task-spec.sh. A malformed fixture would silently mislead a vendor,
#     so we hard-fail BEFORE running any evals if any fixture fails the floor.
#   - The fixture is the ORACLE. Per fixture: reset _workdir per the Rollback
#     Plan, invoke the adapter, then extract-and-run the fixture's own
#     "## Exit Check" bash block (which calls the "## Success Criteria" evals).
#     No golden outputs are needed.
#   - Selective conformance via CONFORMANCE.yaml ("waived: [C5, C6]"). Waived
#     clauses report WAIVE, not PASS. Waiving a load-bearing clause hard-fails.
#   - Dual report: results.json (array of per-fixture objects) AND one line per
#     fixture to stdout. Exit code = count of non-waived failures, so
#     "run_conformance.sh && echo CERTIFIED" gates directly.
#
# Usage:
#   bash run_conformance.sh [--adapter PATH] [--help]

set -euo pipefail

# --- Paths ---
CONF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$CONF_DIR/../.." && pwd)"
VALIDATOR="$SKILL_DIR/scripts/validate-task-spec.sh"
WORKDIR="$CONF_DIR/_workdir"
RESULTS_JSON="$CONF_DIR/results.json"
WAIVER_FILE="$CONF_DIR/CONFORMANCE.yaml"
DEFAULT_ADAPTER="$CONF_DIR/adapters/self.sh"

# --- Clause map (fixture stem → contract clause id), per README.md table ---
clause_for() {
  case "$1" in
    T-conformance-001-status-lock)        echo "C1" ;;
    T-conformance-002-emit-enum)          echo "C12" ;;
    T-conformance-003-no-signed-off-mod)  echo "C6" ;;
    T-conformance-004-execution-backend)  echo "C8" ;;
    T-conformance-005-budget-stop)        echo "C13,C16" ;;
    T-conformance-006-do-not-touch)       echo "C5" ;;
    *)                                    echo "C?" ;;
  esac
}

# --- Load-bearing clauses (README.md: "Engines that waive C5, C6, or C12 are
# NOT conformant"). Waiving any of these is a hard failure. ---
LOAD_BEARING="C5 C6 C12"

is_load_bearing() {
  local clause="$1" lb
  for lb in $LOAD_BEARING; do
    [[ "$clause" == *"$lb"* ]] && return 0
  done
  return 1
}

# --- Arg parsing ---
ADAPTER=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --adapter) ADAPTER="${2:?--adapter requires a path}"; shift 2 ;;
    --adapter=*) ADAPTER="${1#*=}"; shift ;;
    --help|-h)
      sed -n '2,30p' "$0"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# --- Resolve adapter: TASKSPEC_ENGINE_CMD > --adapter > default ---
if [[ -n "${TASKSPEC_ENGINE_CMD:-}" ]]; then
  ADAPTER_CMD="$TASKSPEC_ENGINE_CMD"
elif [[ -n "$ADAPTER" ]]; then
  ADAPTER_CMD="$ADAPTER"
else
  ADAPTER_CMD="$DEFAULT_ADAPTER"
fi

# A bare adapter path must be executable; a compound TASKSPEC_ENGINE_CMD is
# run via the shell, so we only existence-check the simple path case.
if [[ "$ADAPTER_CMD" != *" "* && ! -x "$ADAPTER_CMD" ]]; then
  echo "FATAL: adapter not executable: $ADAPTER_CMD" >&2
  exit 1
fi

# --- Parse waiver list from CONFORMANCE.yaml ("waived: [C5, C6]") ---
WAIVED=""
if [[ -f "$WAIVER_FILE" ]]; then
  WAIVED="$(grep -E '^\s*waived\s*:' "$WAIVER_FILE" \
    | sed -E 's/^\s*waived\s*:\s*//; s/[][]//g; s/,/ /g' \
    | tr -s ' ' || true)"
fi

is_waived() {
  local clause="$1" w part
  for w in $WAIVED; do
    for part in ${clause//,/ }; do
      [[ "$w" == "$part" ]] && return 0
    done
  done
  return 1
}

# --- extract_bash_block: heredoc-aware fenced ```bash extractor for a named
# section. Ported from scripts/run-task-spec.sh (same G7 heredoc-safety logic)
# so the driver reads fixtures exactly the way the skill's own runner does. ---
extract_bash_block() {
  local file="$1" section="$2"
  awk -v want="$section" '
    function strip(s){ gsub(/^[ \t]+|[ \t]+$/, "", s); return s }
    BEGIN { in_section=0; in_block=0; hd=""; top_fence=0 }
    {
      line=$0
      lower=tolower(strip(line))
      if (in_block) {
        if (hd != "") {
          if (strip(line) == hd) { hd="" }
          print line; next
        }
        if (line ~ /^```$/) { exit }
        if (match(line, /<<-?[ \t]*["'"'"']?[A-Za-z_][A-Za-z0-9_]*["'"'"']?/)) {
          d=substr(line, RSTART, RLENGTH)
          gsub(/^<<-?[ \t]*["'"'"']?/, "", d)
          gsub(/["'"'"']?$/, "", d)
          hd=d
        }
        print line; next
      }
      if (in_section) {
        if (line ~ /^```bash$/) { in_block=1; next }
        if (line ~ /^## /) { exit }
        next
      }
      if (top_fence) {
        if (line ~ /^```$/) top_fence=0
        next
      }
      if (line ~ /^```/) { top_fence=1; next }
      if (lower == "## " want) { in_section=1 }
    }
  ' "$file"
}

# --- Reset _workdir per a fixture's Rollback Plan. The fixtures all say
# "delete/truncate the _workdir artifact(s) and re-run", so a clean slate per
# fixture is the faithful reset. ---
reset_workdir_for() {
  local stem="$1"
  case "$stem" in
    T-conformance-001-status-lock)        rm -f "$WORKDIR/c001.log" ;;
    T-conformance-002-emit-enum)          rm -f "$WORKDIR/c002_metrics.jsonl" ;;
    T-conformance-003-no-signed-off-mod)  rm -f "$WORKDIR/c003_envelope_before.txt" "$WORKDIR/c003_envelope_after.txt" ;;
    T-conformance-004-execution-backend)  rm -f "$WORKDIR/c004_metrics.jsonl" ;;
    T-conformance-005-budget-stop)        rm -f "$WORKDIR/c005_iterations.log" ;;
    T-conformance-006-do-not-touch)       rm -f "$WORKDIR/c006_attempt.log" ;;
  esac
}

# --- JSON string escaper (no python3 dependency for the few fields we emit) ---
json_str() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  printf '"%s"' "$s"
}

# ===========================================================================
# Discover fixtures
# ===========================================================================
# Discover fixtures into FIXTURES[]. Uses a while-read loop (NOT mapfile) so the
# conformance suite runs on the bash-3.2 portability floor — a vendor on macOS
# system bash must be able to run it. mapfile/readarray are bash-4-only and on
# 3.2 would print "mapfile: command not found", leave FIXTURES empty, and (under
# this script's flow) report success while testing nothing.
FIXTURES=()
while IFS= read -r _f; do
  [[ -n "$_f" ]] && FIXTURES+=("$_f")
done < <(find "$CONF_DIR" -maxdepth 1 -name 'T-conformance-*.md' | sort)
if [[ ${#FIXTURES[@]} -eq 0 ]]; then
  echo "FATAL: no T-conformance-*.md fixtures found in $CONF_DIR" >&2
  exit 1
fi

# ===========================================================================
# SELF-TEST FLOOR — every fixture must itself validate, BEFORE any engine work.
# A malformed fixture that does not validate would silently mislead a vendor.
# ===========================================================================
echo "== self-test floor: validating ${#FIXTURES[@]} conformance fixtures =="
floor_failed=0
for f in "${FIXTURES[@]}"; do
  set +e
  vout=$(bash "$VALIDATOR" --skip-touches-paths --skip-id-filename "$f" 2>&1)
  vrc=$?
  set -e
  if [[ $vrc -ne 0 ]]; then
    echo "FLOOR-FAIL: $(basename "$f") did not pass validate-task-spec.sh (exit $vrc)" >&2
    echo "$vout" | sed 's/^/    /' >&2
    floor_failed=$((floor_failed + 1))
  fi
done
if [[ $floor_failed -gt 0 ]]; then
  echo "FATAL: $floor_failed conformance fixture(s) failed the self-test floor." >&2
  echo "Refusing to run evals against malformed fixtures." >&2
  exit 1
fi
echo "   self-test floor: all ${#FIXTURES[@]} fixtures valid"
echo ""

# ===========================================================================
# Per-fixture conformance loop
# ===========================================================================
echo "== running conformance (adapter: $ADAPTER_CMD) =="
mkdir -p "$WORKDIR"

NON_WAIVED_FAILURES=0
json_entries=()

for f in "${FIXTURES[@]}"; do
  stem="$(basename "$f" .md)"
  clause="$(clause_for "$stem")"
  reason=""

  # --- Selective conformance: waived clauses do not run evals ---
  if is_waived "$clause"; then
    if is_load_bearing "$clause"; then
      echo "FATAL: load-bearing clause $clause ($stem) cannot be waived (README: not conformant)." >&2
      exit 1
    fi
    reason="$(grep -E '^\s*reason\s*:' "$WAIVER_FILE" 2>/dev/null | head -1 | sed -E 's/^\s*reason\s*:\s*//' || true)"
    [[ -z "$reason" ]] && reason="waived in CONFORMANCE.yaml"
    printf 'WAIVE  %-9s %s\n' "$clause" "$stem"
    json_entries+=("$(printf '{"clause":%s,"fixture":%s,"verdict":"WAIVE","evals_passed":0,"evals_failed":0,"waiver_reason":%s,"duration_sec":0}' \
      "$(json_str "$clause")" "$(json_str "$stem")" "$(json_str "$reason")")")
    continue
  fi

  start=$(date +%s)

  # --- Reset _workdir per the fixture's Rollback Plan ---
  reset_workdir_for "$stem"

  # --- Invoke the adapter (black-box engine call) ---
  set +e
  if [[ "$ADAPTER_CMD" == *" "* ]]; then
    bash -c "$ADAPTER_CMD \"\$1\" \"\$2\" \"\$3\"" _ "$f" "$WORKDIR" "$stem" >/dev/null 2>&1
  else
    "$ADAPTER_CMD" "$f" "$WORKDIR" "$stem" >/dev/null 2>&1
  fi
  adapter_rc=$?
  set -e

  # --- Extract the fixture's own eval chain (Success Criteria + Exit Check) ---
  sc_bash="$(extract_bash_block "$f" "success criteria")"
  ec_bash="$(extract_bash_block "$f" "exit check")"

  evals_passed=0
  evals_failed=0
  verdict="FAIL"

  if [[ $adapter_rc -ne 0 ]]; then
    reason="adapter exited $adapter_rc"
  elif [[ -z "$sc_bash" || -z "$ec_bash" ]]; then
    reason="missing Success Criteria or Exit Check bash block"
  else
    # Per-eval breakdown (advisory counts for the report).
    defined_evals=$(echo "$sc_bash" | grep -oE 'eval_[0-9]+\(\)' | sed 's/()//' | sort -u || true)
    for ev in $defined_evals; do
      if ( cd "$SKILL_DIR" && bash -c "set -euo pipefail; $sc_bash"$'\n'"$ev" ) >/dev/null 2>&1; then
        evals_passed=$((evals_passed + 1))
      else
        evals_failed=$((evals_failed + 1))
      fi
    done
    # The Exit Check is the verdict (the fixture is the oracle).
    if ( cd "$SKILL_DIR" && bash -c "set -euo pipefail; $sc_bash"$'\n'"$ec_bash" ) >/dev/null 2>&1; then
      verdict="PASS"
    else
      verdict="FAIL"
      [[ -z "$reason" ]] && reason="Exit Check returned non-zero"
    fi
  fi

  end=$(date +%s)
  dur=$((end - start))

  printf '%-6s %-9s %s\n' "$verdict" "$clause" "$stem"
  if [[ "$verdict" == "FAIL" ]]; then
    NON_WAIVED_FAILURES=$((NON_WAIVED_FAILURES + 1))
  fi

  json_entries+=("$(printf '{"clause":%s,"fixture":%s,"verdict":%s,"evals_passed":%d,"evals_failed":%d,"waiver_reason":%s,"duration_sec":%d}' \
    "$(json_str "$clause")" "$(json_str "$stem")" "$(json_str "$verdict")" \
    "$evals_passed" "$evals_failed" "$(json_str "$reason")" "$dur")")
done

# ===========================================================================
# Write results.json (array of per-fixture objects)
# ===========================================================================
# Remove any pre-existing file/symlink at the predictable temp path BEFORE the
# redirect, so a planted symlink cannot redirect the write to another target
# (the redirect `>` follows an existing symlink). The post-write checks below
# then confirm a fresh regular file was actually produced.
rm -f "$RESULTS_JSON.tmp.$$" 2>/dev/null
{
  echo "["
  for i in "${!json_entries[@]}"; do
    if [[ $i -lt $(( ${#json_entries[@]} - 1 )) ]]; then
      echo "  ${json_entries[$i]},"
    else
      echo "  ${json_entries[$i]}"
    fi
  done
  echo "]"
} > "$RESULTS_JSON.tmp.$$" 2>/dev/null
# A redirect failure on a brace group does NOT trip set -e on bash 3.2 (it does
# on bash 4+), and `$?` after the group reflects the last INNER command (the
# echo), not the redirect — so we verify the WRITE actually happened by checking
# the temp file, then atomically place it. Fail LOUD on any miss; never report a
# green conformance run whose machine-readable artifact silently went stale.
#   - temp not a non-empty file : the redirect failed (no space / unwritable dir)
#   - RESULTS_JSON is a dir      : mv would move INTO it instead of replacing
#   - mv failure / result not a file : could not place the artifact
if [[ ! -s "$RESULTS_JSON.tmp.$$" ]] \
   || [[ -d "$RESULTS_JSON" ]] \
   || ! mv -f "$RESULTS_JSON.tmp.$$" "$RESULTS_JSON" 2>/dev/null \
   || [[ ! -f "$RESULTS_JSON" ]]; then
  rm -f "$RESULTS_JSON.tmp.$$" 2>/dev/null
  echo "FATAL: could not write results to $RESULTS_JSON (unwritable, no space, or path is a directory)" >&2
  exit 1
fi

echo ""
echo "== results written to $RESULTS_JSON =="
echo "== non-waived failures: $NON_WAIVED_FAILURES =="

exit "$NON_WAIVED_FAILURES"
