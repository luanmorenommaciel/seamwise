---
id: T-20260603-inverted-jq
title: Inverted jq length count with echo 0 fallback
status: ready
format_version: 2
effort: S
budget_iterations: 15
agent: any
depends_on: []
touches_paths:
  - README.md
source_note: WS-B fixture
created: 2026-06-03T00:00:00Z
tags: [fixture]
owner: (none)
priority: P2
severity: cosmetic
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

# Inverted jq length count with echo 0 fallback

> **Why:** jq is not grep -c or wc, so the per-command fast-paths don't fire; the umbrella rule must catch any $(cmd) || echo 0 before a numeric compare

## Goal
Synthetic v2.1.1 fixture used by tests/test-task-spec-skill.sh --suite fixtures.

## Context
WS-B oracle entry; expected verdict declared in tests/fixtures/oracle.json.

## Success Criteria
```bash
eval_1() {
  count=$(jq '. | length' < /nonexistent.json || echo 0)
  [ "$count" -eq 0 ]
}
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
  max_iterations: 15
  circuit_breaker_no_progress: 3
  on_terminal_failure: park_with_context
agent_contract:
  version: 2
  read: [intent, contract, guardrails, operations]
  produce:
    - code
  required_tools: [bash]
  timeout_minutes: 30
  sandbox_type: host
  output_artifacts: []
  mcp_dependencies: []
  emit:
    - pass
    - fail
  backend_metadata: {}
```

## Exit Check
```bash
eval_1
```

## Rollback Plan
(none — fixture)

## Observability Hooks
(none — fixture)

## Anti-Patterns
- **Don't ship this fixture** — regression test only.
- **Don't bypass with --skip flags** — lint must fire under defaults.
- **Don't trust the eval** — the whole point is the lint catching it.

## Do-Not-Touch
- src/

## Open Questions
(none — fixture)
