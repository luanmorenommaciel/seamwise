---
id: T-20260602-conformance-005-budget-stop
title: Conformance — MUST stop iteration at budget_iterations (C13, C16)
status: ready
format_version: 2
effort: S
budget_iterations: 2
agent: any
depends_on: []
touches_paths:
  - tests/conformance/_workdir/c005_iterations.log
source_note: WS-G conformance fixture for agent-contract C13/C16
created: 2026-06-02T00:00:00Z
tags: [conformance, contract, c13, c16]
owner: (none)
priority: P0
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

# Conformance — MUST stop iteration at budget_iterations (C13, C16)

> **Why:** Exercises agent-contract clauses C13 ("An engine MUST stop
> iteration when `budget_iterations` is exhausted") and C16 ("An engine
> MUST NOT loop forever"). The budget gate is non-negotiable.

## Goal

Demonstrate that, given `budget_iterations: 2` and an eval that always
fails, the engine attempts at most 2 iterations, then transitions status
to `parked` with reason `budget`. It MUST NOT attempt a 3rd iteration.

## Context

This is a VENDORED conformance fixture. The eval below is designed to
NEVER pass (it checks for a sentinel value that does not exist). A
conformant engine appends one line per iteration to the log; a passing run
contains exactly 2 lines.

## Success Criteria

```bash
eval_1() {
  test -f tests/conformance/_workdir/c005_iterations.log
}

eval_2() {
  test "$(wc -l < tests/conformance/_workdir/c005_iterations.log)" -le 2
}

eval_3() {
  test "$(wc -l < tests/conformance/_workdir/c005_iterations.log)" -ge 1
}

eval_4() {
  ! grep -q 'NEVER_PASSES_SENTINEL_VALUE_DO_NOT_ADD' README.md
}
```

## Validation Card

```yaml
success_criteria:
  - id: eval_1
    description: iteration log exists
    runnable: bash
    check_type: deterministic
    terminal: false
    expected_duration_sec: 1
  - id: eval_2
    description: at most 2 iterations occurred
    runnable: bash
    check_type: deterministic
    terminal: false
    expected_duration_sec: 1
  - id: eval_3
    description: at least 1 iteration occurred
    runnable: bash
    check_type: deterministic
    terminal: false
    expected_duration_sec: 1
  - id: eval_4
    description: the always-failing eval (the engine kept trying because of this)
    runnable: bash
    check_type: deterministic
    terminal: true
    expected_duration_sec: 1
retry_policy:
  max_iterations: 2
  circuit_breaker_no_progress: 2
  on_terminal_failure: park_with_context
agent_contract:
  version: 2
  read: [intent, contract, guardrails, operations]
  produce:
    - tests
  required_tools: [bash, grep, wc]
  timeout_minutes: 10
  sandbox_type: host
  output_artifacts:
    - path: tests/conformance/_workdir/c005_iterations.log
      type: log
  mcp_dependencies: []
  emit:
    - parked_with_context
    - fail
  backend_metadata: {}
```

## Exit Check

```bash
eval_1 && eval_2 && eval_3
```

(Note: `eval_4` is the always-failing eval that triggers the budget
exhaustion; it is not part of the exit check — the exit check confirms
the engine respected the budget, not that the failing eval passed.)

## Rollback Plan

Delete `tests/conformance/_workdir/c005_iterations.log` and re-run.

## Observability Hooks

Engine MUST emit `parked_with_context` with reason `budget` on the final
ledger entry.

## Anti-Patterns

- **Don't extend the budget on the fly** — `budget_iterations` is contractual.
- **Don't conflate `circuit_breaker_no_progress` with `budget_iterations`** — both stop iteration, but for different reasons; the budget gate is the hard cap.
- **Don't retry after `parked`** — once parked, the task requires human triage.

## Do-Not-Touch

- src/
- tasks/
- .claude/skills/task-spec/references/

## Open Questions

(none — fixture)
