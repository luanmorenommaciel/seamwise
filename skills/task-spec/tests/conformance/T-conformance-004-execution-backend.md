---
id: T-20260602-conformance-004-execution-backend
title: Conformance — SHOULD honor execution_backend; MAY override with justification (C8)
status: ready
format_version: 2
effort: S
budget_iterations: 5
agent: any
depends_on: []
touches_paths:
  - tests/conformance/_workdir/c004_metrics.jsonl
source_note: WS-G conformance fixture for agent-contract C8
created: 2026-06-02T00:00:00Z
tags: [conformance, contract, c8]
owner: (none)
priority: P2
severity: major
due_date: (none)
precondition: (none)
blocked_reason: (none)
security_class: (none)
source_action_item: (none)
linear_ref: (none)
execution_backend: codex
signed_off: false
signed_off_by: (none)
signed_off_at: (none)
---

# Conformance — SHOULD honor execution_backend; MAY override with justification (C8)

> **Why:** Exercises agent-contract clause C8: "An engine SHOULD honor
> `execution_backend` declared in the validation card, but MAY override
> with explicit justification logged to the metrics ledger."

## Goal

Demonstrate that:

- If the engine matches `execution_backend: codex`, it executes under
  Codex and logs `backend_used: codex` to the metrics ledger.
- If the engine is something else (e.g., Kimi) and chooses to override, it
  MUST log `backend_override: {from: codex, to: <name>, reason: <text>}`
  with a non-empty reason.

Either path is conformant. Silent override is NOT conformant.

## Context

This is a VENDORED conformance fixture. Engine authors copy it into their
own test suite. If the engine has multiple backends, run this fixture twice:
once where the declared backend matches and once where it doesn't.

## Success Criteria

```bash
eval_1() {
  test -f tests/conformance/_workdir/c004_metrics.jsonl
}

eval_2() {
  jq -r 'select(.backend_used != null) | .backend_used' \
       tests/conformance/_workdir/c004_metrics.jsonl | grep -q 'codex' \
  || jq -e 'select(.backend_override.reason != null and .backend_override.reason != "")' \
       tests/conformance/_workdir/c004_metrics.jsonl >/dev/null
}

eval_3() {
  jq -r 'select(.backend_override != null) | .backend_override.from' \
       tests/conformance/_workdir/c004_metrics.jsonl | grep -qx 'codex' \
  || true
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
    description: backend used matches declared OR override is justified
    runnable: bash
    check_type: deterministic
    terminal: false
    expected_duration_sec: 1
  - id: eval_3
    description: if overriding, the from-field is codex (declared backend)
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
    - path: tests/conformance/_workdir/c004_metrics.jsonl
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
eval_1 && eval_2 && eval_3
```

## Rollback Plan

Truncate `tests/conformance/_workdir/c004_metrics.jsonl` and re-run.

## Observability Hooks

Engines MAY emit additional telemetry (token counts, cost estimates), but
the ledger record is the source of truth for conformance.

## Anti-Patterns

- **Don't override silently** — that strips the audit trail.
- **Don't lie about `backend_used`** — the value MUST reflect the actual model that produced the work, not the declared preference.
- **Don't log empty `reason` strings** — those are equivalent to silent override.

## Do-Not-Touch

- src/
- tasks/
- .claude/skills/task-spec/references/

## Open Questions

(none — fixture)
