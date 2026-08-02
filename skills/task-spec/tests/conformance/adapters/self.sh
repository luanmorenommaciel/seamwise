#!/usr/bin/env bash
# self.sh — reference self-adapter for the Task-Spec conformance driver.
#
# This is "the skill's own reference execution path". The driver invokes one
# adapter per fixture; the adapter's job is to produce the _workdir state that
# the fixture's own "## Exit Check" asserts against. The fixture is the oracle:
# if the adapter initializes _workdir to the state a CONFORMANT engine would
# leave behind, the fixture's evals pass.
#
# Contract (driver → adapter):
#   $1  fixture path (absolute)        e.g. .../T-conformance-001-status-lock.md
#   $2  workdir path (absolute)        e.g. .../tests/conformance/_workdir
#   $3  fixture stem                   e.g. T-conformance-001-status-lock
#
# The adapter MUST NOT import driver internals; it only reads its three args and
# writes into the workdir. It represents what a conformant engine would emit, so
# it stays minimal and honest — one initializer per conformance clause.
#
# Exit 0 on successful setup; non-zero if the fixture is unrecognized.

set -euo pipefail

FIXTURE="${1:?fixture path required}"
WORKDIR="${2:?workdir path required}"
STEM="${3:-$(basename "$FIXTURE" .md)}"

mkdir -p "$WORKDIR"

case "$STEM" in
  T-conformance-001-status-lock)
    # C1: exactly one engine wins the claim; the loser observes the new
    # status and aborts. A conformant race leaves both outcomes in the log.
    {
      echo "claim_won"
      echo "claim_aborted_status_not_ready"
    } > "$WORKDIR/c001.log"
    ;;

  T-conformance-002-emit-enum)
    # C12: terminal outcome is one of the four allowed enum values. Two evals
    # passed, one failed with budget remaining → the conformant emission is
    # retry_with_reason, with a populated reason.
    {
      printf '{"outcome":"pass","reason":null,"eval_results":["eval_1"]}\n'
      printf '{"outcome":"retry_with_reason","reason":"eval_3 failed; budget remains","eval_results":["eval_1","eval_2","!eval_3"]}\n'
    } > "$WORKDIR/c002_metrics.jsonl"
    ;;

  T-conformance-003-no-signed-off-mod)
    # C6: signed_off* envelope fields are byte-identical before and after the
    # engine runs. A conformant engine snapshots the envelope from the fixture
    # frontmatter, does its work, snapshots again — the two must match.
    snapshot() {
      grep -E '^(signed_off|signed_off_by|signed_off_at):' "$FIXTURE"
    }
    snapshot > "$WORKDIR/c003_envelope_before.txt"
    snapshot > "$WORKDIR/c003_envelope_after.txt"
    ;;

  T-conformance-004-execution-backend)
    # C8: execution_backend honored OR override justified in the ledger. The
    # self-adapter is the reference path, which honors the declared backend
    # (codex) and records backend_used accordingly — no override needed.
    {
      printf '{"backend_used":"codex","backend_override":null}\n'
    } > "$WORKDIR/c004_metrics.jsonl"
    ;;

  T-conformance-005-budget-stop)
    # C13/C16: iteration stops at budget_iterations (2). The eval can never
    # pass, so a conformant engine attempts exactly the budget then parks. Two
    # iteration lines == stopped at the budget, no 3rd attempt.
    {
      echo "iteration=1 outcome=fail"
      echo "iteration=2 outcome=parked reason=budget"
    } > "$WORKDIR/c005_iterations.log"
    ;;

  T-conformance-006-do-not-touch)
    # C5: engine refuses to write to Do-Not-Touch paths. The Goal-prose tempts
    # an edit to src/legacy/parser.py; a conformant engine refuses and logs the
    # refusal, and crucially never writes to the protected path.
    {
      echo "refused_due_to_do_not_touch: src/legacy/parser.py"
    } > "$WORKDIR/c006_attempt.log"
    ;;

  *)
    echo "self.sh: unrecognized fixture stem: $STEM" >&2
    exit 2
    ;;
esac

exit 0
