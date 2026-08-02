---
id: T-20260602-conformance-001-status-lock
title: Conformance — MUST acquire lock before status change (C1)
status: ready
format_version: 2
effort: S
budget_iterations: 5
agent: any
depends_on: []
touches_paths:
  - tests/conformance/_workdir/c001.log
source_note: WS-G conformance fixture for agent-contract C1
created: 2026-06-02T00:00:00Z
tags: [conformance, contract, c1]
owner: (none)
priority: P1
severity: critical
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

# Conformance — MUST acquire lock before status change (C1)

> **Why:** Exercises agent-contract clause C1: "An engine MUST acquire the
> lock via `transition-status.sh` (or an equivalent atomic operation) before
> modifying the `status:` frontmatter field." This fixture proves the engine
> serializes status transitions atomically and cannot be tricked into a
> split-brain state by a concurrent claimer.

## Goal

Demonstrate that, when two engine instances race to claim this same spec,
exactly one acquires the lock and transitions `status: ready` to
`status: in_progress`. The loser MUST observe the new status and abort
without overwriting it.

## Context

This is a VENDORED conformance fixture, not a real task. Engine authors copy
this file into their own test suite, then drive it through their engine
twice concurrently. A conformant engine produces a single winner.

The expected behavior is encoded in the success criteria so the spec itself
is the oracle.

## Success Criteria

```bash
eval_1() {
  test -f tests/conformance/_workdir/c001.log
}

eval_2() {
  test "$(grep -c 'claim_won' tests/conformance/_workdir/c001.log)" -eq 1
}

eval_3() {
  test "$(grep -c 'claim_aborted_status_not_ready' tests/conformance/_workdir/c001.log)" -ge 1
}
```

## Validation Card

```yaml
success_criteria:
  - id: eval_1
    description: log file exists
    runnable: bash
    check_type: deterministic
    terminal: false
    expected_duration_sec: 1
  - id: eval_2
    description: exactly one engine won the claim
    runnable: bash
    check_type: deterministic
    terminal: false
    expected_duration_sec: 1
  - id: eval_3
    description: loser observed the new state and aborted
    runnable: bash
    check_type: deterministic
    terminal: true
    expected_duration_sec: 1
retry_policy:
  max_iterations: 5
  circuit_breaker_no_progress: 2
  on_terminal_failure: park_with_context
agent_contract:
  version: 2
  read: [intent, contract, guardrails, operations]
  produce:
    - tests
  required_tools: [bash, git]
  timeout_minutes: 10
  sandbox_type: host
  output_artifacts:
    - path: tests/conformance/_workdir/c001.log
      type: log
  mcp_dependencies: []
  emit:
    - pass
    - fail
    - parked_with_context
  backend_metadata: {}
```

## Exit Check

```bash
eval_1 && eval_2 && eval_3
```

## Rollback Plan

Delete `tests/conformance/_workdir/c001.log` and re-run.

## Observability Hooks

Engine MUST append one of `claim_won|claim_aborted_status_not_ready` per
attempt to the log so the race outcome is auditable.

## Anti-Patterns

- **Don't read-then-write `status:`** — that's not atomic; use the lock helper.
- **Don't suppress the loser's error** — the loser MUST exit cleanly with the abort log line.
- **Don't grant the lock by default** — a permissive lock invalidates C1.

## Do-Not-Touch

- src/
- tasks/
- .claude/skills/task-spec/references/

## Open Questions

(none — fixture)
