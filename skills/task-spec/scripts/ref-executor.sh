#!/usr/bin/env bash
# ref-executor.sh — the canonical reference Task-Spec EXECUTOR (L2-conformant).
#
# This is NOT an AI agent. It is the smallest possible thing that honors the
# Task-Spec consumer contract end-to-end, so that:
#   1. conformance-check.sh --self-test has a known-good target, and
#   2. adapter authors have a 60-line worked example of "what an executor does."
#
# The contract it honors (mirrors the on_pickup / per_iteration / on_terminal
# blocks in README's "agent contract"):
#   on pickup        : status ready → in-progress  (acquire the lock)
#   per iteration    : attempt the work, then run the Exit Check
#   on success       : status → done
#   on budget exhaust: status → parked  (with a blocked_reason)
#
# Its "work" is deliberately dumb: it reads the Goal and, if the Goal asks it to
# write a literal string into a file (the conformance solvable spec), it does so.
# A real executor swaps this one block for an AI agent / build tool. Everything
# else — the lifecycle, the budget loop, the park — is the part that MATTERS and
# is identical for any executor.
#
# Usage: bash ref-executor.sh <path/to/T-*.md>

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "$SCRIPT_DIR/_lib.sh"
ts_version_flag "$@"

SPEC="${1:?usage: ref-executor.sh <spec-path>}"
[[ -f "$SPEC" ]] || { echo "no such spec: $SPEC" >&2; exit 2; }

GIT_ROOT=$(cd "$(dirname "$SPEC")" && git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")
export GIT_ROOT

set_status() { ts_set_frontmatter_field "$SPEC" "status" "$1"; }
budget=$(grep -m1 '^budget_iterations:' "$SPEC" | awk '{print $2}'); budget="${budget:-10}"

# --- on pickup: acquire the lock ---
set_status "in-progress"

# --- the swappable "work" block (a real executor calls an AI agent here) ---
attempt_work() {
  # Heuristic for the reference fixtures: if the Goal says write `done` into a
  # marker file, do exactly that. Anything else, this dumb executor cannot do
  # (so an unsolvable spec naturally exhausts budget → park).
  if grep -qiE 'write the literal text .?done.? into .?src/marker\.txt' "$SPEC"; then
    mkdir -p "$GIT_ROOT/src"
    printf 'done\n' > "$GIT_ROOT/src/marker.txt"
  fi
}

# --- per-iteration loop, bounded by budget_iterations ---
i=0
while [[ $i -lt $budget ]]; do
  i=$((i + 1))
  attempt_work
  if bash "$SCRIPT_DIR/run-task-spec.sh" "$SPEC" >/dev/null 2>&1; then
    # --- on success: release as done ---
    set_status "done"
    echo "ref-executor: PASS after $i iteration(s) → status: done"
    exit 0
  fi
done

# --- on budget exhaustion: park with context (never loop forever) ---
ts_set_frontmatter_field "$SPEC" "blocked_reason" "budget_iterations ($budget) exhausted without a passing Exit Check"
set_status "parked"
echo "ref-executor: budget exhausted after $i iteration(s) → status: parked"
exit 0
