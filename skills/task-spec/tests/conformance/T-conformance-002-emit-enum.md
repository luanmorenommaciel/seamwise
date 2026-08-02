---
id: T-20260602-conformance-002-emit-enum
title: Conformance — MUST emit one of the four terminal states (C12)
status: ready
format_version: 2
effort: S
budget_iterations: 5
agent: any
depends_on: []
touches_paths:
  - tests/conformance/_workdir/c002_metrics.jsonl
source_note: WS-G conformance fixture for agent-contract C12
created: 2026-06-02T00:00:00Z
tags: [conformance, contract, c12]
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

# Conformance — MUST emit one of the four terminal states (C12)

> **Why:** Exercises agent-contract clause C12: "An engine MUST emit exactly
> one of `{pass, fail, retry_with_reason, parked_with_context}` per
> attempt." Downstream consumers depend on this closed set; a rogue value
> like `error` or `unknown` breaks every ledger reader.

## Goal

Demonstrate that, given three evals where two pass and one fails (with
budget remaining), the engine emits `retry_with_reason` — not `error`,
`fail_with_message`, `incomplete`, or any other value outside the four-value
enum.

## Context

This is a VENDORED conformance fixture. Engine authors copy it into their
own test suite, run it through their engine, and inspect the metrics ledger
line they produced. The ledger MUST contain a JSON record whose `outcome`
field is one of the four allowed strings.

## Success Criteria

```bash
eval_1() {
  test -f tests/conformance/_workdir/c002_metrics.jsonl
}

eval_2() {
  jq -r '.outcome' tests/conformance/_workdir/c002_metrics.jsonl \
    | grep -Eq '^(pass|fail|retry_with_reason|parked_with_context)$'
}

eval_3() {
  jq -r '.outcome' tests/conformance/_workdir/c002_metrics.jsonl \
    | tail -1 | grep -qx 'retry_with_reason'
}

eval_4() {
  test "$(jq -r '.reason' tests/conformance/_workdir/c002_metrics.jsonl | tail -1)" != "null"
}
```

## Validation Card

```yaml
success_criteria:
  - id: eval_1
    description: ledger exists
    runnable: bash
    check_type: deterministic
    terminal: false
    expected_duration_sec: 1
  - id: eval_2
    description: every outcome is in the four-value enum
    runnable: bash
    check_type: deterministic
    terminal: false
    expected_duration_sec: 1
  - id: eval_3
    description: last outcome is retry_with_reason
    runnable: bash
    check_type: deterministic
    terminal: false
    expected_duration_sec: 1
  - id: eval_4
    description: reason field is populated
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
  required_tools: [bash, jq]
  timeout_minutes: 10
  sandbox_type: host
  output_artifacts:
    - path: tests/conformance/_workdir/c002_metrics.jsonl
      type: log
  mcp_dependencies: []
  emit:
    - pass
    - fail
    - retry_with_reason
    - parked_with_context
  backend_metadata: {}
```

## Exit Check

```bash
eval_1 && eval_2 && eval_3 && eval_4
```

## Rollback Plan

Truncate `tests/conformance/_workdir/c002_metrics.jsonl` and re-run.

## Observability Hooks

Engine MUST write one JSON record per attempt with at least
`{outcome, reason, eval_results}` keys.

## Anti-Patterns

- **Don't invent new outcomes** (`error`, `incomplete`, `aborted`). Use the four allowed values.
- **Don't conflate `fail` with `retry_with_reason`** — `fail` is "evals failed and engine surrenders this attempt"; `retry_with_reason` is "evals failed and engine will retry, here is why".
- **Don't omit `reason`** when emitting `retry_with_reason` — that defeats the auditability story.

## Do-Not-Touch

- src/
- tasks/
- .claude/skills/task-spec/references/

## Open Questions

(none — fixture)
